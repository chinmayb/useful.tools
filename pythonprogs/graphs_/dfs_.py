from constants import graph1, graph2


def dfs_recursive(graph, start_node, visited=[]):
    """
    * Add to the visited array
    * Call the dfs method recursively, with the next non-visited node
      by looping through all the nodes connected to it.
    """
    visited.append(start_node)

    for next_node in graph[start_node]:
        if next_node not in visited:
            dfs_recursive(graph, next_node, visited)

    return visited


def dfs_stack(graph, start_node):
    visited, stack = [], [start_node]
    while stack:
        vertex = stack.pop()
        if vertex not in visited:
            visited.append(vertex)
            stack.extend(graph[vertex])
    return visited

#print dfs_recursive(graph2, '0')
#print dfs_stack(graph2, '0')

print dfs_recursive(graph1, 'C')
print dfs_stack(graph1, 'C')