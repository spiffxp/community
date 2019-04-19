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

""" This script does things with sigs.yaml. I'm curious if this will be
    less awful than using jq+bash to consume it, or hacking up the existing
    generator/app.go file
"""

import argparse
import ruamel.yaml as yaml
import json

update_gha_repos_template = """
update gha_repos set repo_group = 'SIG {}' where name in (
{}
);
"""

def repos_from_sig(sig):
    """Returns a list of org/repos given a sig"""
    repos = {}
    subprojects = sig.get('subprojects', [])
    if subprojects is None:
        subprojects = []
    for sp in subprojects:
        for uri in sp['owners']:
            # TODO(spiffxp): this should really be matching root OWNERS
            repo = '/'.join(uri.split('/')[3:5])
            if repo != '':
                repos[repo] = True
    return sorted(repos.keys())
    
def write_repo_groups_sql(sigs, fp):
    for sig in sigs['sigs']:
        repos = repos_from_sig(sig)
        if 'kubernetes/kubernetes' in repos:
            repos.remove('kubernetes/kubernetes')
        if len(repos):
            fp.write(
                update_gha_repos_template.format(
                    sig['name'], 
                    ',\n'.join(['  \'{}\''.format(r) for r in repos])))

# TODO: kubernetes/kubernetes, kubernetes/api, kubernetes/client-go
def print_repos_owned_by_multiple_sigs(sigs):
    """Repos should only fall under a single sig; print any that don't"""
    repos = {}
    for sig in sigs['sigs']:
        name = sig['name']
        sig_repos = repos_from_sig(sig)
        for repo in sig_repos:
            owning_sigs = repos.get(repo, [])
            owning_sigs.append(name)
            repos[repo] = owning_sigs

    for repo, owning_sigs in sorted(
            repos.items(), key=lambda (k,v): len(v), reverse=True):
        if len(owning_sigs) > 1:
            print '{} is owned by {} sigs ({})'.format(repo, len(owning_sigs), owning_sigs)

def main(sigs_yaml, repo_groups_sql, validate_sigs):
    """/shrug."""

    with open(sigs_yaml) as fp:
        sigs = yaml.round_trip_load(fp)

    if repo_groups_sql is not None:
        with open(repo_groups_sql, 'w') as fp:
            write_repo_groups_sql(sigs, fp)
    
    if validate_sigs:
        print_repos_owned_by_multiple_sigs(sigs)

if __name__ == '__main__':
    PARSER = argparse.ArgumentParser(
        description='Do things with sigs.yaml')
    PARSER.add_argument(
        '--sigs-yaml',
        default='./sigs.yaml',
        help='Path to sigs.yaml')
    PARSER.add_argument(
        '--repo-groups-sql',
        help='Path to output repo_groups.sql if provided')
    PARSER.add_argument(
        '--validate-sigs',
        action='store_true',
        help='Print repos owned by multiple sigs if true')
    ARGS = PARSER.parse_args()

    main(ARGS.sigs_yaml, ARGS.repo_groups_sql, ARGS.validate_sigs)

