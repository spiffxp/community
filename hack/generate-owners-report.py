#!/usr/bin/env python3

# Copyright 2019 The Kubernetes Authors.
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
This will:
- shallow clone the given list of orgs into a dir (default: no)
- parse all OWNERS files from that dir into owners.yaml (default: no)
    - aliases are expanded
    - repos published staging use kubernetes/kubernetes/OWNERS_ALIASES
    - approvers are removed from reviewers
- load owners.yaml and sigs.yaml
- create a placeholder "unknown" subproject under committee steering
- assign each OWNERS file to a subproject that shares a common prefix;
  if none, assign to "unknown"
- output to stdout a new sigs.yaml that has everything assigned with
  comments to explain why OWNERS files are where they are

nb:
- these comments will get stripped by the golang generator
- it's committee-steering's duty to divest itself of ownership of these files

Example usage:
    ./hack/generate-owners-report.py \
        --refresh-owners \
        --owners-yaml owners.yaml \
        --sigs-yaml sigs.yaml \
        --refresh-repos \
        --repo-path ~/repo-dir kubernetes{-client,-csi,-incubator,-sigs,} \
        > sigs-with-all-owners.yaml
"""

import argparse
import glob
import logging
import os
import re
import sys

import requests
import ruamel.yaml
from sh import find, git, cp, rm
from pygtrie import StringTrie


yaml = ruamel.yaml.YAML()

def mkdirp(path):
    if not os.path.exists(path):
        os.makedirs(path)

# entries:[a,b,c], aliases:{a:[d,e,f],b:[e,g]} -> [d,e,f,g,c]
def expand_aliases(entries, aliases):
    """Expands aliases in entries"""
    expanded=set()
    if entries == None:
        entries = []
    if aliases == None:
        aliases = {}
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

# uri: https://raw.*/org/repo/master/path -> org/repo/path
def monorepo_path_from_raw_gh_uri(uri):
    return re.sub(r"https://raw.githubusercontent.com/(.*)/master/(.*)",r"\1/\2",uri)

# uri: org/repo/path -> https://raw.*/org/repo/master/path
def raw_gh_uri_from_monorepo_path(path):
    return re.sub(r"([^/]+)/(.*)",r"https://raw.githubusercontent.com/\1/master/\2",path)

def repos_from_k8s_group(k8s_group):
    """Returns a list of org/repos given a kubernetes community group"""
    repos = {}
    subprojects = k8s_group.get('subprojects', [])
    if subprojects is None:
        subprojects = []
    for sp in subprojects:
        for uri in sp['owners']:
            owners_path = monorepo_path_from_raw_gh_uri(uri)
            path_parts = owners_path.split('/')
            # org/repo is owned by k8s_group if org/repo/OWNERS os in one of their subprojects
            if path_parts[2] == 'OWNERS':
                repo = '/'.join(path_parts[0:2])
                repos[repo] = True
    return sorted(repos.keys())

def subprojects_from_k8s_group(k8s_group):
    """Returns subprojects given a kubernetes community group
       - convert owners uri list to set of monorepo paths
       - add parent attribute to subprojects (eg: sig-foo, wg-bar)
    """
    subprojects = k8s_group.get('subprojects', [])
    if subprojects is None:
        subprojects = []
    for sp in subprojects:
        sp['parent'] = k8s_group['dir']
        sp['full_name'] = sp['parent'] + "/" + sp['name']
        sp['owners'] = [monorepo_path_from_raw_gh_uri(uri) for uri in sp['owners']]
    return subprojects

def k8s_group_name(k8s_group):
    """Returns human readable name for a given kubernetes community group, eg:
        - sig-foo -> SIG Foo
        - committee-bar -> Bar Committee
    """
    group_dir = k8s_group.get('dir', '')
    if group_dir.startswith('sig-'):
        return "SIG " + k8s_group['name']
    if group_dir.startswith('committee-'):
        return k8s_group['name'] + " Committee"
    return "UNKNOWN " + group_dir

def load_owners_yaml(owners_yaml_path):
    if os.path.exists(owners_yaml_path):
        with open(owners_yaml_path) as fp:
            owners = yaml.load(fp)
    if owners is None:
        owners = {'owners':{},'aliases':{}}
    return owners

def load_all_owners(owners_yaml_path, paths, refresh_owners):
    """Returns a dict of all loaded OWNERS and OWNERS_ALIASES, via these steps:
        - if owners.yaml exists and refresh=False, return parsed owners.yaml
        - otherwise parse OWNERS/OWNERS_ALIASES files for most paths not already in owners.yaml
            - allow vendor/OWNERS (eg: dep-approvers)
            - ignore vendor/.*/OWNERS (we ignore vendored OWNERS)
        - dereferences any aliases in OWNERS files
        - remove 'filters' keys, they're too much complexity for our analysis here
    eg: {   aliases:
                org/repo/OWNERS_ALIASES:
                    alias1: [foo, bar]
                    alias2: [baz, qux]
            owners: 
                org/repo/path/to/OWNERS:
                    approvers: [baz, qux]
                    reviewers: [foo, bar]
                    labels: [sig/testing, area/prow] }
    """
    
    # load owners.yaml if it exists for cacghed/pre-loaded results
    all_owners = load_owners_yaml(owners_yaml_path)

    if not refresh_owners:
        return all_owners

    logging.info(f"refresh_owners is {refresh_owners}")

    # ignore OWNERS files in vendored repos, but catch vendor/OWNERS
    ignore_owners_path_regex=re.compile('vendor/.*/OWNERS')

    # first pass: load in all OWNERS and OWNERS_ALIAS files if not already loaded
    for path in paths:
        base = os.path.basename(path)
        logging.info(f"Finding all OWNERS files in {path}")
        file_paths = []
        # use `find` instead of python's glob (which falls prey to symlink loops that exist in k/k)
        for file_path in find(path, "-type", "f", "-name", "OWNERS*", _iter=True):
            if len(ignore_owners_path_regex.findall(file_path)) == 0:
                file_paths.append(file_path.strip())
        file_paths.sort()
        for file_path in file_paths:
            # pretend like we're in a monorepo whose layout is org/repo/files
            monorepo_path = file_path[file_path.find(path)+len(path)-len(base):]
            key = 'aliases' if file_path.endswith('ALIASES') else 'owners'
            logging.info(monorepo_path)
            if monorepo_path not in all_owners[key]:
                with open(file_path.strip()) as fp:
                    owners_yaml = yaml.load(fp)
                # parse '.*' filters, ignore the rest
                if 'filters' in owners_yaml:
                    filters = owners_yaml.pop('filters')
                    all_filter = filters.get('.*', {})
                    owners_yaml['approvers'] = all_filter.get('approvers',[])
                    owners_yaml['reviewers'] = all_filter.get('reviewers',[])
                all_owners[key][monorepo_path] = owners_yaml

    # second pass: expand aliases if not already expanded
    for owners_path in all_owners['owners'].keys():
        owners = all_owners['owners'][owners_path]
        if owners.get('expanded', False):
            continue
        repo = '/'.join(owners_path.split('/')[:2])
        aliases_path = f"{repo}/OWNERS_ALIASES"
        aliases_yaml = all_owners['aliases'].get(aliases_path,{})
        aliases = aliases_yaml.get('aliases',{})
        for k in ['approvers','reviewers']:
            logging.info(f"expanding {k} for {owners_path} using {aliases_path}")
            owners[k] = expand_aliases(owners.get(k,[]), aliases)
        owners['expanded'] = True
        all_owners['owners'][owners_path] = owners

    return all_owners

def prune_dupe_reviewers(all_owners):
    pruned_owners = all_owners.copy()
    for path, owners in pruned_owners['owners'].items():
        for a in owners['approvers']:
            if a in owners['reviewers']:
                owners['reviewers'].remove(a)

    return pruned_owners

def load_all_groups_and_subprojects(sigs_yaml):
    """ Returns two dicts:
        all_groups: {sig-foo: [subproject1, subproject2], ...}
        all_subprojects: {subproject1: {name: subproject1, ...}, ...}
    """ 

    all_groups = {}
    for group_type in sigs_yaml.keys():
        for g in sigs_yaml[group_type]:
            all_groups[g['dir']] = g


    all_subprojects = {}
    # only sigs and committees are allowed to own code (aka subprojects)
    for group_type in ['sigs', 'committees']:
        for g in sigs_yaml[group_type]:
            subprojects = subprojects_from_k8s_group(g)
            for sp in subprojects:
                sp_name = sp['name']
                if sp_name in subprojects:
                    logging.warn(f"subproject {sp_name} already exists")
                all_subprojects[sp['name']] = sp

    # create a placeholder subproject to assign unknown gaps, aka OWNERS files
    # that are not, or wouldn't be covered by, existing subproject OWNERS files 
    all_subprojects['unknown'] = {
        'name': 'unknown',
        'description': 'placeholder subproject to catch any OWNERS files not covered by other subprojects',
        'parent': 'committee-steering',
        'full_name': 'committee-steering/unknown',
        'owners': []
    }
    all_groups['committee-steering']['subprojects'].append(all_subprojects['unknown'])

    return (all_groups, all_subprojects)

def load_all_repos(repo_path, orgs, refresh_repos):
    mkdirp(repo_path)
    paths = [os.path.join(repo_path, org) for org in orgs]
    if refresh_repos:
        for org in orgs:
            rm("-rf", os.path.join(repo_path, org))
            req = requests.get(f"https://api.github.com/orgs/{org}/repos?per_page=100")
            repos = req.json()
            for repo in repos:
                git_url = repo['git_url']
                target_dir = os.path.join(repo_path, org, repo['name'])
                mkdirp(target_dir)
                git.clone("--depth", "1", git_url, target_dir)
    return paths

def copy_k8s_aliases_to_staged_repos(repo_path):
    k8s_repo_path = os.path.join(repo_path, "kubernetes", "kubernetes")
    g = k8s_repo_path+"/staging/src/k8s.io/*"
    for d in glob.glob(g):
        repo = d.split('/')[-1]
        staged_repo_path = os.path.join(repo_path, "kubernetes", repo)
        cp(os.path.join(k8s_repo_path, "OWNERS_ALIASES"), os.path.join(staged_repo_path, "OWNERS_ALIASES"))

def main(owners_yaml_path, sigs_yaml_path, repo_path, orgs, refresh_owners, refresh_repos):

    paths = load_all_repos(repo_path, orgs, refresh_repos)
    
    copy_k8s_aliases_to_staged_repos(repo_path)

    all_owners = load_all_owners(owners_yaml_path, paths, refresh_owners)

    all_owners = prune_dupe_reviewers(all_owners)

    with open(owners_yaml_path, 'w') as fp:
        yaml.dump(all_owners, fp)

    with open(sigs_yaml_path) as fp:
        sigs_yaml = yaml.load(fp)
    
    all_groups, all_subprojects = load_all_groups_and_subprojects(sigs_yaml)

    owners_to_subprojects = {} # path: {name: n, [reason: r]}
    owners_trie = StringTrie(separator='/')
    
    # first pass: populate known owner->subproject mappings from sigs.yaml
    for _, sp in all_subprojects.items():
        for owners_path in sp['owners']:
            owners_to_subprojects[owners_path] = {'name': sp['name']}
            owners_trie[owners_path.replace("/OWNERS","")] = sp['name']

    # TODO(spiffxp): how to handle sig ownership? eg:
    # - k/k/test/e2e is owned by testing-commons, but k/k/test/e2e/foo is owned by sig-foo
    # - k/t/config/jobs is owned by test-infra, but k/t/config/jobs/kubernetes/foo is owned by sig-foo
    # - k/c is owned by community, but k/c/sig-foo is owned by sig-foo
    #
    # sig-foo should be approvers of that subdir, but testing-commons may have
    # an overriding say; how should we represent this?
    # - explicitly list over in sig-foo subproject, mention it overlaps with testing-commons
    # - explicitly list in testing-commons subproject under some 'affects' field or smth
    # - create top-level "meta" subprojects for each sig
    # - allow for the fact that the check can derive this info as coverage enough

    # second pass: take a guess based on longest prefix
    for owners_path in all_owners['owners'].keys():
        if owners_path not in owners_to_subprojects:
            path_prefix, subproject = owners_trie.longest_prefix(owners_path.replace("/OWNERS",""))
            if subproject is None:
                subproject = 'unknown'
            full_name = all_subprojects[subproject]['full_name']
            owners_to_subprojects[owners_path] = {'name': subproject, 'reason': f"longest prefix match: {path_prefix} implies ownership by {full_name}"}

    # now go back and populate subprojects with our guesses
    for _, sp in all_subprojects.items():
        sp['guesses'] = []
        sp['owners'] = ruamel.yaml.comments.CommentedSeq()

    for owners_path, guess in owners_to_subprojects.items():
        name = guess.pop('name')
        sp = all_subprojects[name]
        guess['path'] = owners_path
        sp['guesses'].append(guess)

    for _, sp in all_subprojects.items():
        for guess in sorted(sp['guesses'], key=lambda x:x['path']):
            # TODO(spiffxp): rewrite sigs.yaml to use monorepo paths
            sp['owners'].append(guess['path'])
            # sp['owners'].append(raw_gh_uri_from_monorepo_path(guess['path']))
            if 'reason' in guess:
                sp['owners'].yaml_add_eol_comment(guess['reason'], len(sp['owners'])-1)
        sp.pop('guesses')

    for group_type in ['sigs', 'committees']:
        for g in sigs_yaml[group_type]:
            for sp in g.get('subprojects',[]):
                sp.pop('parent')
                sp.pop('full_name')
                sp['owners'] = all_subprojects[sp['name']]['owners']

    # yaml.dump(owners_to_subprojects, sys.stdout)
    # yaml.dump(all_subprojects, sys.stdout)
    yaml.dump(sigs_yaml, sys.stdout)

def setup_logging():
    """Initialize logging to screen"""
    # See https://docs.python.org/2/library/logging.html#logrecord-attributes
    # [IWEF]mmdd HH:MM:SS.mmm] msg
    fmt = '%(levelname).1s%(asctime)s.%(msecs)03d] %(message)s'
    datefmt = '%m%d %H:%M:%S'
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
    )

if __name__ == '__main__':
    setup_logging()

    parser = argparse.ArgumentParser(description='Generate some reports on OWNERS files')
    parser.add_argument('--sigs-yaml', default='sigs.yaml', help='Path to sigs.yaml')
    parser.add_argument('--owners-yaml', default='owners.yaml', help='Path to read/write parsed owners files')
    parser.add_argument('--refresh-owners-yaml', dest='refresh_owners', action='store_true', help='Refresh owners.yaml based on repos')
    parser.add_argument('--no-refresh-owners-yaml', dest='refresh_owners', action='store_false', help='Do not walk paths, just load owners.yaml')
    parser.set_defaults(refresh_owners_yaml=True)
    parser.add_argument('--repo-path', default='/tmp/repo-path', help='path to clone repos to')
    parser.add_argument('--refresh-repos', dest='refresh_repos', action='store_true', help='refresh all repos')
    parser.add_argument('--no-refresh-repos', dest='refresh_repos', action='store_false', help='do not refresh all repos')
    parser.set_defaults(refresh_repos=False)
    parser.add_argument('paths', metavar='path', type=str, nargs='+', help='paths to search for owners files')

    args = parser.parse_args()

    main(args.owners_yaml, args.sigs_yaml, args.repo_path, args.paths, args.refresh_owners_yaml, args.refresh_repos)
