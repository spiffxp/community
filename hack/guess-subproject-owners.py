#!/usr/bin/env python3

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

"""
Attempt at verifying whether we have subproject owners. Does this by
looking at all OWNERS files, and augmenting sigs.yaml with the union
and intersection of all OWNERS files for a given subproject.

A well formed subproject has people and labels in the intersection of
all OWNERS files. Ideally we would enforce this somehow, but for now
this is just an attempt at surveying how good or bad we are at
adhering to this criteria.

This has been hacked together over time and so shouldn't be seen as
a final quality product, but rather a starting point to decide if this
is the right direction for us to head.
"""

import argparse
import json
import logging
import os
import re
import sys
import tempfile

import requests
from ruamel.yaml import YAML
from sh import wget


yaml = YAML()

# lazy caching: get the file if it doesn't exist
def get_cached_file(dest_file, uri):
    logging.debug("local: %s, remote: %s", dest_file, uri)
    if not os.path.exists(dest_file):
        dest_path = os.path.dirname(dest_file)
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)
        req = requests.get(uri)
        content = req.text.replace('\t', ' ')
        owners = yaml.load(content) if req.ok else {'present': False}
        if owners.get('present', None) is None:
            owners['present'] = True
        with open(dest_file, 'w') as fp:
            yaml.dump(owners, fp)

# expanding aliases is terrible and horrible, that is all
def expand_owners_aliases(entries, aliases):
    expanded=set()
    for x in entries:
        if x in aliases:
            ax = aliases[x]
            if ax is None:
                ax=[]
            expanded.update(ax)
        else:
            if x is not None:
                expanded.add(x)
    return list(expanded)

def process_sig_subproject(sig, sp):
    logging.info("%s/%s" % (sig['dir'], sp['name']))
    paths = sp.get('paths', {})
    for uri in sp['owners']:
        dest_file = re.sub(r"https://raw.githubusercontent.com/(.*)/master/(.*)",r"\1/\2",uri)
        alias_uri = re.sub(r"(.*)/master/(.*)",r"\1/master/OWNERS_ALIASES",uri)
        dest_alias_file = re.sub(r"https://raw.githubusercontent.com/(.*)/master/(.*)",r"\1/\2",alias_uri)
        get_cached_file(dest_file, uri)
        get_cached_file(dest_alias_file, alias_uri)
        # lazy caching: dump the file contents into sigs.yaml if they're not there already
        if dest_file in paths:
            continue
        with open(dest_file) as ofp, open(dest_alias_file) as afp:
            owners = yaml.load(ofp)
            aliases = yaml.load(afp).get('aliases',{})
        for k in ['approvers','reviewers']:
            owners[k] = expand_owners_aliases(owners.get(k,[]), aliases)
        paths[dest_file] = owners
    sp['paths'] = paths

def main(sigs_yaml, workdir):
    if workdir is None:
        workdir = tempfile.mkdtemp(prefix='verify-subproject-owners')

    with open(sigs_yaml) as fp:
        groups = yaml.load(fp)
    
    cwd = os.getcwd()
    os.chdir(workdir)

    sigs = groups['sigs']

    # lazy caching: ensure all owners file contents are in sigs.yaml
    logging.info("LOADING....")
    for sig in sigs:
        subprojects = sig.get('subprojects', [])
        for sp in subprojects:
            process_sig_subproject(sig, sp)

    # now we can do some analysis
    logging.info("ANALYSIS....")
    for sig in sigs:
        subprojects = sig.get('subprojects', [])
        if subprojects is None:
            subprojects = []
        for sp in subprojects:
            sp_id="%s/%s" % (sig['dir'],sp['name'])
            # logging.info("sigs/%s/%s" % (sig['dir'], sp['name']))
            # presence of owners files
            if all(owners['present'] == False for path,owners in sp['paths'].items()):
                logging.warn("WARNING: %s is missing ALL of its OWNERS files, why is this a subproject?" % sp_id)
            if any(owners['present'] == False for path,owners in sp['paths'].items()):
                for path,owners in sp['paths'].items():
                    if not owners['present']:
                        logging.warn("WARNING: %s is missing %s" % (sp_id,path))
            
            # do the owners files have a label corresponding to the sig

            # are there common approvers across all
            common=sp.get('common',{})
            union=sp.get('union',{})
            for k in ['approvers','reviewers','labels']:
                vs = [set(owners.get(k,[])) for path, owners in sp['paths'].items()]
                common[k] = list(set.intersection(*vs))
                union[k] = list(set.union(*vs))
                if len(sp['paths']) > 1:
                    if len(common[k]) != len(union[k]) and len(common[k]) == 0:
                        logging.warn("WARNING: %s has no common %s" % (sp_id, k))
                    else:
                        logging.info("OK: %s has %d common %s" % (sp_id, len(common[k]), k))

            sp['common'] = common
            sp['union'] = union


    os.chdir(cwd)
    with open(sigs_yaml, 'w') as fp:
        yaml.dump(groups, fp)

def setup_logging():
    """Initialize logging to screen"""
    # See https://docs.python.org/2/library/logging.html#logrecord-attributes
    # [IWEF]mmdd HH:MM:SS.mmm] msg
    fmt = '%(levelname).1s%(asctime)s.%(msecs)03d] %(message)s'  # pylint: disable=line-too-long
    datefmt = '%m%d %H:%M:%S'
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
    )

if __name__ == '__main__':
    setup_logging()

    parser = argparse.ArgumentParser(description='Do things with sigs.yaml')
    parser.add_argument('--sigs-yaml', default='../sigs.yaml', help='Path to sigs.yaml')
    parser.add_argument('--workdir', default=None)
    args = parser.parse_args()

    main(args.sigs_yaml, args.workdir)

# dump all owners files into a dir

# dump all owners files listed in subprojects into a dir

# expand all owners files in a dir based on OWNERS_ALIASES
