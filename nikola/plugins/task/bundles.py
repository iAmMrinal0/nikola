# -*- coding: utf-8 -*-

# Copyright © 2012-2015 Roberto Alsina and others.

# Permission is hereby granted, free of charge, to any
# person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the
# Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice
# shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
# OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import unicode_literals

import json
import os

try:
    import webassets
except ImportError:
    webassets = None  # NOQA

from nikola.plugin_categories import LateTask
from nikola import utils


class BuildBundles(LateTask):
    """Bundle assets using WebAssets."""

    name = "create_bundles"

    def set_site(self, site):
        cdnjs_path = os.path.join(os.path.dirname(__file__), 'cdnjsdata.json')
        with open(cdnjs_path) as fd:
            self.cdnjs = json.load(fd)
        self.logger = utils.get_logger('bundles', site.loghandlers)
        if webassets is None and site.config['USE_BUNDLES']:
            utils.req_missing(['webassets'], 'USE_BUNDLES', optional=True)
            self.logger.warn('Setting USE_BUNDLES to False.')
            site.config['USE_BUNDLES'] = False
        self.cdn_js_urls = []
        self.cdn_css_urls = []
            
        super(BuildBundles, self).set_site(site)

    def url_from_entry(self, entry):
        """Turn a bundles entry into a URL from cdnjs"""
        if entry in self.cdnjs:
            url = self.cdnjs[entry]
        elif '::' in entry:
            # It's like twitter-bootstrap::bootstrap.css
            # The 1st part is in cdnjs but the name in the URL is different
            key, fname = entry.split('::')
            url = self.cdnjs[key]
            url = '/'.join(url.split('/')[:-1]) + '/' + fname
        else:
            url = None
        return url

    def gen_tasks(self):
        """Bundle assets using WebAssets."""

        kw = {
            'filters': self.site.config['FILTERS'],
            'output_folder': self.site.config['OUTPUT_FOLDER'],
            'cache_folder': self.site.config['CACHE_FOLDER'],
            'theme_bundles': get_theme_bundles(self.site.THEMES),
            'themes': self.site.THEMES,
            'files_folders': self.site.config['FILES_FOLDERS'],
            'code_color_scheme': self.site.config['CODE_COLOR_SCHEME'],
            'use_cdn': self.site.config['USE_CDN'],
        }

        def build_bundle(output, inputs):
            out_dir = os.path.join(kw['output_folder'],
                                   os.path.dirname(output))
            inputs = [os.path.relpath(i, out_dir) for i in inputs if os.path.isfile(i)]
            cache_dir = os.path.join(kw['cache_folder'], 'webassets')
            utils.makedirs(cache_dir)
            env = webassets.Environment(out_dir, os.path.dirname(output),
                                        cache=cache_dir)
            if inputs:
                bundle = webassets.Bundle(*inputs, output=os.path.basename(output))
                env.register(output, bundle)
                # This generates the file
                try:
                    env[output].urls()
                except Exception as e:
                    self.logger.error("Failed to build bundles.")
                    self.logger.exception(e)
                    self.logger.notice("Try running ``nikola clean`` and building again.")
            else:
                with open(os.path.join(out_dir, os.path.basename(output)), 'wb+'):
                    pass  # Create empty file

        yield self.group_task()
        if (webassets is not None and self.site.config['USE_BUNDLES'] is not
                False):
            for name, _files in kw['theme_bundles'].items():
                
                # If using a CDN, remove those files that will be delivered by the CDN
                t_files = []
                if kw['use_cdn']:
                    # Using a CDN, move CDN-able files into cdn_*_url lists
                    for i in _files:
                        url = self.url_from_entry(i)
                        if url is None:
                            t_files.append(i)
                        else:
                            if url.endswith('js'):
                                cdn_js_urls.append(url)
                            else:
                                cdn_css_urls.append(url)
                else:  # No CDN, remove the package::file notation
                    for i in _files:
                        if '::' in i:
                            i = i.split('::')[-1]
                        t_files.append(i)
                        
                _files = t_files
                    
                output_path = os.path.join(kw['output_folder'], name)
                dname = os.path.dirname(name)
                files = []
                for fname in _files:
                    # paths are relative to dirname
                    files.append(os.path.join(dname, fname))
                file_dep = [os.path.join(kw['output_folder'], fname)
                            for fname in files if
                            utils.get_asset_path(fname, self.site.THEMES, self.site.config['FILES_FOLDERS']) or fname == os.path.join('assets', 'css', 'code.css')]
                # code.css will be generated by us if it does not exist in
                # FILES_FOLDERS or theme assets.  It is guaranteed that the
                # generation will happen before this task.
                task = {
                    'file_dep': list(file_dep),
                    'task_dep': ['copy_assets', 'copy_files'],
                    'basename': str(self.name),
                    'name': str(output_path),
                    'actions': [(build_bundle, (name, file_dep))],
                    'targets': [output_path],
                    'uptodate': [
                        utils.config_changed({
                            1: kw,
                            2: file_dep
                        }, 'nikola.plugins.task.bundles')],
                    'clean': True,
                }
                yield utils.apply_filters(task, kw['filters'])


def get_theme_bundles(themes):
    """Given a theme chain, return the bundle definitions."""
    bundles = {}
    for theme_name in themes:
        bundles_path = os.path.join(
            utils.get_theme_path(theme_name), 'bundles')
        if os.path.isfile(bundles_path):
            with open(bundles_path) as fd:
                for line in fd:
                    try:
                        name, files = line.split('=')
                        files = [f.strip() for f in files.split(',')]
                        bundles[name.strip().replace('/', os.sep)] = files
                    except ValueError:
                        # for empty lines
                        pass
                break
    return bundles
