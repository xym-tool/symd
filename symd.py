#!/usr/bin/python
##############################################################################
# Copyright (c) 2015 Cisco Systems  All rights reserved.
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License v1.0 which accompanies this distribution,
# and is available at http://www.eclipse.org/legal/epl-v10.html
##############################################################################
from __future__ import print_function  # Must be at the beginning of the file
import matplotlib.pyplot as plt
import networkx as nx
import argparse
import glob
import sys
import re

__author__ = "Jan Medved"
__copyright__ = "Copyright(c) 2015, Cisco Systems, Inc."
__license__ = "Eclipse Public License v1.0"
__email__ = "jmedved@cisco.com"

G = nx.DiGraph()

# Regular expressions for parsing yang files; we are only interested in
# the 'module', 'import' and 'revision' statements
MODULE_STATEMENT = re.compile('''^[ \t]*(sub)?module +(["'])?([-A-Za-z0-9]*(@[0-9-]*)?)(["'])? *\{.*$''')
IMPORT_STATEMENT = re.compile('''^[ \t]*import[\s]*([-A-Za-z0-9]*)?[\s]*\{([\s]*prefix[\s]*[\S]*;[\s]*})?.*$''')
INCLUDE_STATEMENT = re.compile('''^[ \t]*include[\s]*([-A-Za-z0-9]*)?[\s]*\{.*$''')
REVISION_STATEMENT = re.compile('''^[ \t]*revision[\s]*(['"])?([-0-9]*)?(['"])?[\s]*\{.*$''')


def warning(s):
    """
    Prints out a warning message to stderr.
    :param s: The warning string to print
    :return: None
    """
    print("WARNING: %s" % s, file=sys.stderr)


def error(s):
    """
    Prints out an error message to stderr.
    :param s: The error string to print
    :return: None
    """
    print("ERROR: %s" % s, file=sys.stderr)


def get_local_yang_files(local_repos):
    """
    Gets the list of all yang module files in the specified local repositories
    :param local_repos: List of local repositories, i.e. directories where
           yang modules may be located
    :return: list of all *.yang files in the local repositories
    """
    yfs = []
    for repo in local_repos:
        if repo.endswith('/'):
            yfs.extend(glob.glob('%s*.yang' % repo))
        else:
            yfs.extend(glob.glob('%s/*.yang' % repo))
    return yfs


def parse_model(lines):
    """
    Parses a yang files for 'module', 'import'/'include' and 'revision'
    statements
    :param lines: Pre-parsed yang files as a list of lines
    :return: module name, module type (module or submodule), list of
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


def get_yang_modules(yfiles):
    """
    Creates a list of yang modules from the specified yang files and stores
    them as nodes in a Networkx directed graph. This function also stores
    node attributes (list of imports, module type, revision, ...) for each
    module in the NetworkX data structures.
    The function uses the global variable G (directed network graph of yang
    model dependencies)
    :param yfiles: List of files containing yang modules
    :return: None; resulting nodes are stored in G.
    """
    for yf in yfiles:
        try:
            with open(yf) as yfd:
                name, mod_type, imports, revisions = parse_model(yfd.readlines())
                if len(revisions) > 0:
                    rev = max(revisions)
                else:
                    error("No revision specified for module '%s', file '%s'" % (name, yf))
                    rev = None
                attr = {'mod_type': mod_type, 'imports': imports, 'revision': rev}
                # IF we already have a module with a lower revision, replace it now
                try:
                    en = G.node[name]
                    en_rev = en['revision']
                    if en_rev:
                        if rev:
                            if rev > en_rev:
                                warning("Replacing revision for module '%s' ('%s' -> '%s')" % (name, en_rev, rev))
                                G.node[name]['attr_dict'] = attr
                    else:
                        if rev:
                            warning("Replacing revision for module '%s' ('%s' -> '%s')" % (name, en_rev, rev))
                            G.node[name]['attr_dict'] = attr
                except KeyError:
                    G.add_node(name, attr_dict=attr)
        except IOError as ioe:
            print(ioe)


def get_module_dependencies():
    """
    Creates the dependencies  between modules (i.e. the edges) in the NetworkX
    directed graph created by 'get_yang_modules()'
    This function uses the global variable G (directed network graph of yang
    modules)
    :return: None
    """
    for node in G.nodes_iter():
        for imp in G.node[node]['imports']:
            try:
                G.node[imp]
                G.add_edge(node, imp)
            except KeyError:
                error("Module '%s': imported module '%s' was not scanned" % (node, imp))


def print_impacting_modules():
    """
    For each module, print a list of modules that the module is depending on,
    i.e. modules whose change can potentially impact the module. The function
    shows all levels of dependency, not just the immediately imported
    modules.
    :return:
    """
    print('\n===Impacting Modules===')
    for node in G.nodes_iter():
        descendants = nx.descendants(G, node)
        print('\n%s:' % node)
        for d in descendants:
            print('    %s' % d)


def print_impacted_modules():
    """
     For each module, print a list of modules that depend on the module, i.e.
     modules that would be impacted by a change in this module. The function
     shows all levels of dependency, not just the immediately impacted
     modules.
    :return:
    """
    print('\n===Impacted Modules===')
    for node in G.nodes_iter():
        ancestors = nx.ancestors(G, node)
        if len(ancestors) > 0:
            print('\n%s:' % node)
            for a in ancestors:
                print('    %s' % a)


def get_subgraph_for_node(node):
    """
    Prints the dependency graph for only the specified node (a full dependency
    graph can be difficult to read).
    :param node: Node for which to print the sub-graph
    :return:
    """
    ancestors = nx.ancestors(G, node)
    ancestors.add(node)
    return nx.subgraph(G, ancestors)


def print_dependents(graph, pl, imports):
    """
    Print the immediate dependencies (imports/includes), and for each
    immediate dependency print its dependencies
    :param graph: Dictionary containing the subgraph of dependencies that
                  we are about to print
    :param pl: Preamble list, list of string to print out before each
               dependency (Provides the offset for higher order dependencies)
    :param imports: List of immediate imports/includes
    :return:
    """
    preamble = ''
    for ps in pl:
        preamble += ps
    print(preamble + '  |')  # Print a newline
    for i in range(len(imports)):
        print((preamble + '  +--> %s') % imports[i])
        # Determine if a dependency has dependencies on its own; if yes,
        # print them out before moving onto the next dependency
        try:
            imp_imports = graph[imports[i]]
            if i < (len(imports) - 1):
                pl.append('  |   ')
            else:
                pl.append('      ')
            print_dependents(graph, pl, imp_imports)
            pl.pop(-1)
            # Only print a newline if we're NOT the last processed module
            if i < (len(imports) - 1):
                print(preamble + '  |')
        except KeyError:
            pass


def get_connected_nodes():
    """
    Remove from the module dependency graph all modules that do not have any
    dependencies (i.e they neither import/include any modules nor are they
    imported/included by any modules)
    :return: the connected module dependency graph
    """
    ng = nx.DiGraph(G)
    for node in G.nodes_iter():
        ancestors = nx.ancestors(G, node)
        descendants = nx.descendants(G, node)
        if len(ancestors) == 0 and len(descendants) == 0:
            ng.remove_node(node)
    return ng


def print_dependency_tree(single_node=None):
    """
    For each module, print the dependency tree for imported modules
    :return:
    """
    print('\n===Imported Modules===')
    for node in G.nodes_iter():
        if single_node and (node!=single_node):
            continue
        dg = nx.dfs_successors(G, node)
        plist = []
        print('\n%s:' % node)
        if len(dg):
            imports = dg[node]
            print_dependents(dg, plist, imports)
            


def get_dependent_modules():
    print('\n===Dependent Modules===')
    for node in G.nodes_iter():
        dependents = nx.bfs_predecessors(G, node)
        if len(dependents):
            print(dependents)


def init(local_repos):
    yang_files = get_local_yang_files(local_repos)
    print("\n*** Scanning %d yang files for 'import' and 'revision' statements..\n" % len(yang_files))
    get_yang_modules(yang_files)
    print('\n*** Found %d yang modules. Creating dependencies...\n' % len(G.nodes()))
    get_module_dependencies()
    print('\nInitialization finished.\n')


def get_connecting_edges(node_set):
    print(node_set)
    el = []
    for edge in G.edges_iter():
        enl = []
        for en in edge:
            enl.append(en)
        print(enl)
        if enl[0] in node_set and enl[1] in node_set:
                el.append(edge)
    print(len(el))
    return el

##############################################################################
# symd - Show Yang Module Dependencies.
#
# A program to analyze dependencies between yang modules
##############################################################################


if __name__ == "__main__":
    # Set matplotlib into no-interactive mode
    plt.interactive(False)

    parser = argparse.ArgumentParser(description='Show the dependency graph for a set of yang models')
    parser.add_argument("--local-repos", default=["./"], nargs='+',
                        help="List of local directories where models are located")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--graph", action='store_true', default=False,
                   help="Plot the overall dependency graph")
    g.add_argument("--sub-graphs", nargs='+', default=[],
                   help="Plot the dependency graphs for the specified modules")
    g.add_argument("--impact-analysis", action='store_true', default=False,
                   help="For each scanned yang module, print the impacting and impacted modules")
    g.add_argument("--dependency-tree", action='store_true', default=False,
                   help="For each scanned yang module, print to stdout its dependency tree, (i.e. show all the modules that it depends on)")
    g.add_argument("--single-dependency-tree", type=str,
                   help="For a single yang module, print to stdout its dependency tree, (i.e. show all the modules that it depends on)")
    args = parser.parse_args()

    init(args.local_repos)

    if args.dependency_tree:
        print_dependency_tree()

    if args.single_dependency_tree:
        print_dependency_tree(single_node=args.single_dependency_tree)

    if args.impact_analysis:
        print_impacting_modules()
        print_impacted_modules()

    if args.graph:
        NG = get_connected_nodes()

        plt.figure(1, figsize=(50, 50))
        print('Drawing the overall dependency graph...')
        nx.draw_networkx(
            NG,
            node_size=200,
            node_shape='s',
            font_size=14,
            node_color='r',
            alpha=0.25,
            linewidths=0.5)
        plt.savefig("modules.png")

    plot_num = 2

    for node in  args.sub_graphs:
        plt.figure(plot_num, figsize=(20, 20))
        plot_num += 1
        print("Plotting graph for module '%s'..." % node)
        try:
            rtg = get_subgraph_for_node(node)
            nx.draw_networkx(
                rtg,
                node_size=150,
                node_shape='s',
                font_size=14,
                node_color='r',
                alpha=0.25,
                linewidths=0.5)
            plt.savefig("%s.png" % node)
            print('    Done.')
        except nx.exception.NetworkXError as e:
            print("    %s" %e)

    print('\n')

    # plt.show()
