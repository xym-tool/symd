##############################################################################
# Copyright (c) 2015 Cisco Systems  All rights reserved.
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License v1.0 which accompanies this distribution,
# and is available at http://www.eclipse.org/legal/epl-v10.html
##############################################################################
from __future__ import print_function  # Must be at the beginning of the file

# On macos, plotting current;y won't work. TBD.
try:
    import matplotlib.pyplot as plt
except:
    pass

import networkx as nx
import glob
import sys
import os
import re
import json

__author__ = "Jan Medved, Einar Nilsen-Nygaard"
__copyright__ = "Copyright(c) 2015, Cisco Systems, Inc."
__license__ = "Eclipse Public License v1.0"
__email__ = "jmedved@cisco.com, einarnn@cisco.com"

G = nx.DiGraph()

# Regular expressions for parsing yang files; we are only interested in
# the 'module', 'import' and 'revision' statements
MODULE_STATEMENT = re.compile('''^[ \t]*(sub)?module +(["'])?([-A-Za-z0-9]*(@[0-9-]*)?)(["'])? *\{.*$''')
IMPORT_STATEMENT = re.compile('''^[ \t]*import[\s]*([-A-Za-z0-9]*)?[\s]*\{([\s]*prefix[\s]*[\S]*;[\s]*})?.*$''')
INCLUDE_STATEMENT = re.compile('''^[ \t]*include[\s]*([-A-Za-z0-9]*)?[\s]*\{.*$''')
REVISION_STATEMENT = re.compile('''^[ \t]*revision[\s]*(['"])?([-0-9]*)?(['"])?[\s]*\{.*$''')

# Node Attribute Types
TAG_ATTR = 'tag'
IMPORT_ATTR = 'imports'
TYPE_ATTR = 'type'
REV_ATTR = 'revision'

# Tags
RFC_TAG = 'rfc'
DRAFT_TAG = 'draft'
UNKNOWN_TAG = 'unknown'


def warning(s, verbose=False):
    """
    Prints out a warning message to stderr.
    :param s: The warning string to print
    :return: None
    """
    if verbose:
        print("WARNING: %s" % s, file=sys.stderr)


def error(s):
    """
    Prints out an error message to stderr.
    :param s: The error string to print
    :return: None
    """
    print("ERROR: %s" % s, file=sys.stderr)


def get_local_yang_files(local_repos, recurse=False):
    """
    Gets the list of all yang module files in the specified local repositories
    :param local_repos: List of local repositories, i.e. directories where
           yang modules may be located
    :return: list of all *.yang files in the local repositories
    """
    yfs = []
    if not recurse:
       for repo in local_repos:
            if repo.endswith('/'):
                yfs.extend(glob.glob('%s*.yang' % repo))
            else:
                yfs.extend(glob.glob('%s/*.yang' % repo))
    else:
        for repo in local_repos:
            for path, sub, files in os.walk(repo, followlinks=True):
                for f in files:
                    if f.endswith('.yang'):
                        yfs.append(os.path.join(path, f))

    return yfs


def parse_yang_module(lines):
    """
    Parses a yang module; look for the 'module', 'import'/'include' and
    'revision' statements
    :param lines: Pre-parsed yang files as a list of lines
    :return: module name, module type (module or sub-module), list of
             imports and list of revisions
    """
    module = None
    mod_type = None
    revisions = []
    imports = []

    for line in lines:
        match = MODULE_STATEMENT.match(line)
        if match:
            module = match.groups()[2]
            if match.groups()[0] == 'sub':
                mod_type = 'sub'
            else:
                mod_type = 'mod'
        match = IMPORT_STATEMENT.match(line)
        if match:
            imports.append(match.groups()[0])
        match = INCLUDE_STATEMENT.match(line)
        if match:
            imports.append(match.groups()[0])
        match = REVISION_STATEMENT.match(line)
        if match:
            revisions.append(match.groups()[1])
    return module, mod_type, imports, revisions


def get_yang_modules(yfiles, tag, verbose=False):
    """
    Creates a list of yang modules from the specified yang files and stores
    them as nodes in a Networkx directed graph. This function also stores
    node attributes (list of imports, tag, revision, ...) for each module
    in the NetworkX data structures. The function uses the global variable
    G (directed network graph of yang model dependencies)
    :param yfiles: List of files containing yang modules
    :param tag: Tag - RFC or draft for now
    :return: None; resulting nodes are stored in G.
    """
    for yf in yfiles:
        try:
            with open(yf) as yfd:
                name, mod_type, imports, revisions = parse_yang_module(yfd.readlines())
                if len(revisions) > 0:
                    rev = max(revisions)
                else:
                    error("No revision specified for module '%s', file '%s'" % (name, yf))
                    rev = None
                attr = {TYPE_ATTR: mod_type, TAG_ATTR: tag, IMPORT_ATTR: imports, REV_ATTR: rev}
                # IF we already have a module with a lower revision, replace it now
                try:
                    en = G.node[name]
                    en_rev = en[REV_ATTR]
                    if en_rev:
                        if rev:
                            if rev > en_rev:
                                warning("Replacing revision for module '%s' ('%s' -> '%s')"
                                        % (name, en_rev, rev),
                                        verbose)
                                G.node[name]['attr_dict'] = attr
                    else:
                        if rev:
                            warning("Replacing revision for module '%s' ('%s' -> '%s')"
                                    % (name, en_rev, rev),
                                    verbose)
                            G.node[name]['attr_dict'] = attr
                except KeyError:
                    G.add_node(name, attr_dict=attr)
        except IOError as ioe:
            print(ioe)


def prune_graph_nodes(graph, tag):
    """
    Filers graph nodes to only nodes that are tagged with the specified tag
    :param graph: Original graph to prune
    :param tag: Tag for nodes of interest
    :return: List of nodes tagged with the specified tag
    """
    node_list = []
    for node_name in graph.nodes_iter():
        try:
            if graph.node[node_name][TAG_ATTR] == tag:
                node_list.append(node_name)
        except KeyError:
            pass
    return node_list


def get_module_dependencies():
    """
    Creates the dependencies  between modules (i.e. the edges) in the NetworkX
    directed graph created by 'get_yang_modules()'
    This function uses the global variable G (directed network graph of yang
    modules)
    :return: None
    """
    for node_name in G.nodes_iter():
        for imp in G.node[node_name][IMPORT_ATTR]:
            if imp in G.node:
                G.add_edge(node_name, imp)
            else:
                error("Module '%s': imports unknown module '%s'" % (node_name, imp))


def get_unknown_modules(verbose=False):
    unknown_nodes = []
    for node_name in G.nodes_iter():
        for imp in G.node[node_name][IMPORT_ATTR]:
            if imp not in G.node:
                unknown_nodes.append(imp)
                warning("Module '%s': imports module '%s' that was not scanned"
                        % (node_name, imp),
                        verbose)
    for un in unknown_nodes:
        attr = {TYPE_ATTR: 'module', TAG_ATTR: UNKNOWN_TAG, IMPORT_ATTR: [], REV_ATTR: None}
        G.add_node(un, attr_dict=attr)


def print_impacting_modules(single_node=None, json_out=None):
    """
    For each module, print a list of modules that the module is depending on,
    i.e. modules whose change can potentially impact the module. The function
    shows all levels of dependency, not just the immediately imported
    modules.  If the json_out argument is not None, then the output will be
    recorded there instead of on stdout.
    :return:
    """
    if json_out is None:
        print('\n===Impacting Modules===')
    else:
        json_out['impacting_modules'] = {}
    for node_name in G.nodes_iter():
        if single_node and (node_name!=single_node):
            continue
        descendants = nx.descendants(G, node_name)
        if json_out is None:
            print(augment_format_string(node_name, '\n%s:') % node_name)
        else:
            json_out['impacting_modules'][node_name] = []
        for d in descendants:
            if json_out is None:
                print(augment_format_string(d, '    %s') % d)
            else:
                json_out['impacting_modules'][node_name].append(d)

def augment_format_string(node_name, fmts):
    """
    Depending on the tag for the specified node, this function will add
    a marker to the specified format string. Tags can currently be 'rfc'
    or 'draft', the marker is '*' (asterisk)
    :param node_name: Node name to query
    :param fmts: format string to augment
    :return: Augmented format string
    """
    module_tag = G.node[node_name][TAG_ATTR]
    if module_tag == RFC_TAG:
        return fmts + ' *'
    if module_tag == UNKNOWN_TAG:
        return fmts + ' (?)'
    return fmts


def print_impacted_modules(single_node=None, json_out=None):
    """
     For each module, print a list of modules that depend on the module, i.e.
     modules that would be impacted by a change in this module. The function
     shows all levels of dependency, not just the immediately impacted
     modules.  If the json_out argument is not None, then the output will be
     recorded there rather than printed on stdout.
    :return:
    """
    if json_out is None:
        print('\n===Impacted Modules===')
    else:
        json_out['impacted_modules'] = {}
    for node_name in G.nodes_iter():
        if single_node and (node_name!=single_node):
            continue
        ancestors = nx.ancestors(G, node_name)
        if len(ancestors) > 0:
            if json_out is None:
                print(augment_format_string(node_name, '\n%s:') % node_name)
            else:
                json_out['impacted_modules'][node_name] = []
            for a in ancestors:
                if json_out is None:
                    print(augment_format_string(a, '    %s') % a)
                else:
                    json_out['impacted_modules'][node_name].append(a)


def get_subgraph_for_node(node_name):
    """
    Prints the dependency graph for only the specified node_name (a full dependency
    graph can be difficult to read).
    :param node_name: Node for which to print the sub-graph
    :return:
    """
    ancestors = nx.ancestors(G, node_name)
    ancestors.add(node_name)
    return nx.subgraph(G, ancestors)


def print_dependents(graph, preamble_list, imports):
    """
    Print the immediate dependencies (imports/includes), and for each
    immediate dependency print its dependencies
    :param graph: Dictionary containing the subgraph of dependencies that
                  we are about to print
    :param preamble_list: Preamble list, list of string to print out before each
               dependency (Provides the offset for higher order dependencies)
    :param imports: List of immediate imports/includes
    :return:
    """
    # Create the preamble string for the current level
    preamble = ''
    for preamble_string in preamble_list:
        preamble += preamble_string
    # Print a newline for the current level
    print(preamble + '  |')
    for i in range(len(imports)):
        print(augment_format_string(imports[i], preamble + '  +--> %s') % imports[i])
        # Determine if a dependency has dependencies on its own; if yes,
        # print them out before moving onto the next dependency
        try:
            imp_imports = graph[imports[i]]
            if i < (len(imports) - 1):
                preamble_list.append('  |   ')
            else:
                preamble_list.append('      ')
            print_dependents(graph, preamble_list, imp_imports)
            preamble_list.pop(-1)
            # Only print a newline if we're NOT the last processed module
            if i < (len(imports) - 1):
                print(preamble + '  |')
        except KeyError:
            pass


def print_dependency_tree():
    """
    For each module, print the dependency tree for imported modules
    :return: None
    """
    print('\n=== Module Dependency Trees ===')
    for node_name in G.nodes_iter():
        if G.node[node_name][TAG_ATTR] != UNKNOWN_TAG:
            dg = nx.dfs_successors(G, node_name)
            plist = []
            print(augment_format_string(node_name, '\n%s:') % node_name)
            if len(dg):
                imports = dg[node_name]
                print_dependents(dg, plist, imports)


def return_dependency_tree_as_json(graph=None, ignore_exact=[], ignore_partial=[], yang_dict={}):
    output = {}
    output['nodes'] = []
    output['links'] = []
    idx_arr = []
    if not graph:
        graph = G
    for node_name in graph.nodes_iter():
        if ignore_exact and (node_name in ignore_exact):
            continue
        if ignore_partial and len(ignore_partial)>0:
            partial_found = False
            for partial in ignore_partial:
                if len(partial)==0:
                    continue
                if node_name and (partial in node_name):
                    partial_found = True
            if partial_found:
                continue
        draft_email = yang_dict.get(node_name, None)
        if draft_email != None:
            output['nodes'].append({'name': node_name, 'email' : draft_email})
        else:
            output['nodes'].append({'name': node_name })

        idx_arr.append(node_name)
    for (z, a) in graph.edges_iter():
        if a in ignore_exact or z in ignore_exact:
            continue
        if len(ignore_partial)>0:
            partial_found = False
            for partial in ignore_partial:
                if len(partial)==0:
                    continue
                if partial in a or partial in z:
                    partial_found = True
            if partial_found:
                continue
        a_idx = idx_arr.index(a)
        z_idx = idx_arr.index(z)
        output['links'].append(
            {
                'source': a_idx,
                'target': z_idx,
                'value': 1.0
            })
    return output

        
def print_dependency_tree_as_json(graph=None, filename=None, ignore_exact=[], ignore_partial=[], yang_dict={}):
    """
    """
    if filename==None:
        print("No filename!")
        sys.exit(1)
    output = return_dependency_tree_as_json(
        graph=graph,
        ignore_exact=ignore_exact,
        ignore_partial=ignore_partial, yang_dict=yang_dict)
    with open(filename, 'w') as f:
        f.write(json.dumps(output, indent=2, sort_keys=True))
        f.close

def print_dependency_emails(graph=None, ignore_exact=[], ignore_partial=[], yang_dict={}):
    """
    """
    output = return_dependency_tree_as_json(
        graph=graph,
        ignore_exact=ignore_exact,
        ignore_partial=ignore_partial, yang_dict=yang_dict)
    emails = set()
    for node in output["nodes"]:
        email = node.get("email", None)
        if email != None:
            emails.add(email)
    for mail in emails:
        print(" %s " % mail)

def prune_standalone_nodes():
    """
    Remove from the module dependency graph all modules that do not have any
    dependencies (i.e they neither import/include any modules nor are they
    imported/included by any modules)
    :return: the connected module dependency graph
    """
    ng = nx.DiGraph(G)
    for node_name in G.nodes_iter():
        ancestors = nx.ancestors(G, node_name)
        descendants = nx.descendants(G, node_name)
        if len(ancestors) == 0 and len(descendants) == 0:
            ng.remove_node(node_name)
    return ng


def get_dependent_modules():
    print('\n===Dependent Modules===')
    for node_name in G.nodes_iter():
        dependents = nx.bfs_predecessors(G, node_name)
        if len(dependents):
            print(dependents)


def init(rfc_repos, draft_repos, recurse=False, verbose=False):
    """
    Initialize the dependency graph
    :param rfc_repos: List of local repositories for yang modules defined in
                      IETF RFCs
    :param draft_repos: List of local repositories for yang modules defined in
                        IETF drafts
    :return: None
    """
    rfc_yang_files = get_local_yang_files(rfc_repos, recurse)
    if verbose:
        print("\n*** Scanning %d RFC yang module files for 'import' and 'revision' statements..."
              % len(rfc_yang_files))
    get_yang_modules(rfc_yang_files, RFC_TAG)
    num_rfc_modules = len(G.nodes())
    if verbose:
        print('\n*** Found %d RFC yang modules.' % num_rfc_modules)

    draft_yang_files = get_local_yang_files(draft_repos, recurse)
    if verbose:
        print("\n*** Scanning %d draft yang module files for 'import' and 'revision' statements..." %
              len(draft_yang_files))
    get_yang_modules(draft_yang_files, DRAFT_TAG)
    num_draft_modules = len(G.nodes()) - num_rfc_modules
    if verbose:
        print('\n*** Found %d draft yang modules.' % num_draft_modules)

    if verbose:
        print("\n*** Analyzing imports...")
    get_unknown_modules(verbose)
    num_unknown_modules = len(G.nodes()) - (num_rfc_modules + num_draft_modules)
    if verbose:
        print('\n*** Found %d imported/included yang modules that were scanned.' % num_unknown_modules)

    if verbose:
        print('\n*** Creating module dependencies...')
    get_module_dependencies()
    if verbose:
        print('\nInitialization finished.\n')


def plot_module_dependency_graph(graph):
    """
    Plot a graph of specified yang modules. this function is used to plot
    both the full dependency graph of all yang modules in the DB, or a
    subgraph of dependencies for a specified module
    :param graph: Graph to be plotted
    :return: None
    """


    # fixed_pos = { 'ietf-interfaces':(0.01,0.01) }
    # fixed_nodes = fixed_pos.keys()
    # pos = nx.spring_layout(graph, iterations=200,
    #                        pos=fixed_pos, fixed=fixed_nodes)
    #pos = nx.circular_layout(graph)

    pos = nx.spring_layout(graph, iterations=2000)

    # Draw RFC nodes (yang modules) in red
    nx.draw_networkx_nodes(graph, pos=pos, nodelist=prune_graph_nodes(graph, RFC_TAG), node_size=200,
                           node_shape='s', node_color='red', alpha=0.5, linewidths=0.5)

    # Draw draft nodes (yang modules) in green
    nx.draw_networkx_nodes(graph, pos=pos, nodelist=prune_graph_nodes(graph, DRAFT_TAG), node_size=200,
                           node_shape='o', node_color='green', alpha=0.5, linewidths=0.5)

    # Draw unknown nodes (yang modules) in orange
    nx.draw_networkx_nodes(graph, pos=pos, nodelist=prune_graph_nodes(graph, UNKNOWN_TAG), node_size=200,
                           node_shape='^', node_color='orange', alpha=1.0, linewidths=0.5)

    # Draw edges in light gray (fairly transparent)
    nx.draw_networkx_edges(graph, pos=pos, alpha=0.25, linewidths=0.1, arrows=False)

    # Draw labels on nodes (modules)
    nx.draw_networkx_labels(graph, pos=pos, font_size=10, font_weight='bold', alpha=1.0)
