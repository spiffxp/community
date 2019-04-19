#!/usr/bin/env python

# Copyright 2018 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" This script does things with github's api, I'm curious if this will
    be less awful than bash+jq
"""

import argparse
import json
import os
import re
import sys
import tempfile

import requests
from ruamel.yaml import YAML
from sh import wget


yaml = YAML()

# lazy caching: get the file if it doesn't exist
def ensure_exists(dest_file, uri):
    print ("ensure %s exists, otherwise download %s" % (dest_file, uri))
    if not os.path.exists(dest_file):
        dest_path = os.path.dirname(dest_file)
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)
        req = requests.get(uri)
        owners = yaml.load(req.content) if req.ok else {'present': False}
        if owners.get('present', None) is None:
            owners['present'] = True
        with open(dest_file, 'w') as fp:
            yaml.dump(owners, fp)

def main(community_yaml, workdir):
    """Loads in sigs.yaml and then dumps it out again
       to prove that round-tripping works"""

    if workdir is None:
        workdir = tempfile.mkdtemp(prefix='verify-subproject-owners')

    with open(community_yaml) as fp:
        groups = yaml.load(fp)
    
    cwd = os.getcwd()
    os.chdir(workdir)

    sigs = groups['sigs']
    aliases = {}

    # lazy caching: ensure all owners file contents are in sigs.yaml
    print("LOADING....")
    for sig in sigs:
        # workaround: sig-ibmcloud owns no code, why do they exist
        if 'subprojects' not in sig:
            print("WARNING: %s has no subprojects, why are they a sig?" % sig['dir'])
        subprojects = sig.get('subprojects', [])
        # workaround: sig-openstack has "subprojects:"
        if subprojects is None:
            print("WARNING: %s has an empty subprojects: field" % sig['dir'])
            subprojects = []
        for sp in subprojects:
            print("%s/%s" % (sig['dir'], sp['name']))
            paths = sp.get('paths', {})
            for uri in sp['owners']:
                dest_file = re.sub(r"https://raw.githubusercontent.com/(.*)/master/(.*)",r"\1/\2",uri)
                alias_uri = re.sub(r"(.*)/master/(.*)",r"\1/master/OWNERS_ALIASES",uri)
                dest_alias_file = re.sub(r"https://raw.githubusercontent.com/(.*)/master/(.*)",r"\1/\2",alias_uri)
                ensure_exists(dest_file, uri)
                ensure_exists(dest_alias_file, alias_uri)
                # lazy caching: dump the file contents into sigs.yaml if they're not there already
                if dest_file not in paths:
                    with open(dest_file) as ofp, open(dest_alias_file) as afp:
                        owners = yaml.load(ofp)
                        # expanding aliases is terrible and horrible, that is all
                        aliases = yaml.load(afp).get('aliases',{})
                        if isinstance(aliases,list):
                            print("WARNING: %s is an invalid OWNERS_ALIAS file" % dest_alias_file)
                        else:
                            for k in ['approvers','reviewers']:
                                if k in owners:
                                    expanded=[]
                                    for x in owners[k]:
                                        if x in aliases:
                                            ax = aliases[x]
                                            if ax is None:
                                                print("WARNING: %s using empty alias %s defined in %s" % (dest_file, x, dest_alias_file))
                                                ax=[]
                                            expanded.extend(ax)
                                        else:
                                            if x is None:
                                                print("WARNING: %s using empty entry" % (dest_file))
                                            else:
                                                expanded.append(x)
                                    owners[k]=expanded
                        paths[dest_file] = owners
            sp['paths'] = paths

    # now we can do some analysis
    print("ANALYSIS....")
    for sig in sigs:
        subprojects = sig.get('subprojects', [])
        if subprojects is None:
            subprojects = []
        for sp in subprojects:
            sp_id="%s/%s" % (sig['dir'],sp['name'])
            # print("sigs/%s/%s" % (sig['dir'], sp['name']))
            # presence of owners files
            if all(owners['present'] == False for path,owners in sp['paths'].iteritems()):
                print("WARNING: %s is missing ALL of its OWNERS files, why is this a subproject?" % sp_id)
            if any(owners['present'] == False for path,owners in sp['paths'].iteritems()):
                for path,owners in sp['paths'].iteritems():
                    if not owners['present']:
                        print("WARNING: %s is missing %s" % (sp_id,path))
            
            # do the owners files have a label corresponding to the sig

            # are there common approvers across all
            common=sp.get('common',{})
            union=sp.get('union',{})
            for k in ['approvers','labels']:
                vs = [set(owners.get(k,[])) for path, owners in sp['paths'].iteritems()]
                common[k] = list(set.intersection(*vs))
                union[k] = list(set.union(*vs))
                if len(sp['paths']) > 1:
                    if len(common[k]) != len(union[k]) and len(common[k]) == 0:
                        print("WARNING: %s has no common %s" % (sp_id, k))
                    else:
                        print("OK: %s has %d common %s" % (sp_id, len(common[k]), k))

            sp['common'] = common
            sp['union'] = union


    os.chdir(cwd)
    with open(community_yaml, 'w') as fp:
        yaml.dump(groups, fp)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Do things with sigs.yaml')
    parser.add_argument('--community-yaml', default='../sigs.yaml', help='Path to sigs.yaml')
    parser.add_argument('--workdir', default=None)
    args = parser.parse_args()

    main(args.community_yaml, args.workdir)


