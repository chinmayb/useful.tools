from collections import defaultdict

class Graphs(object):
    """
    Represent a graph
    """
    def __init__(self, connections, _directed=False):
        self._graph = defaultdict(set)
        self._directed = _directed
        self.add_connections(connections)

    @property
    def nodecount(self):
        return len(self._graph.keys())

    def values(self):
        return [list(x) for x in self._graph.values()]

    def keys(self):
        return [x for x in self._graph.keys()]

    def add_connections(self, connections):
        for n1, n2 in connections:
            self.add(n1, n2)

    def add(self, n1, n2):
        self._graph[n1].add(n2)

    def remove(self, n1, n2):
        pass

    def __str__(self):
        return "%s" % dict(self._graph)

    def find_all_paths(self, n1, n2, path=[], all_paths=[]):
        """
        Returns the newest path
        #FIXME
        """
        path = path + [n1]

        if n2 == n1:
            return path
        if n1 not in self._graph:
            return

        for node in self._graph[n1]:
            if node not in path:
                new_path = self.find_all_paths(node, n2, path, all_paths)
                if new_path and new_path not in all_paths:
                    all_paths.append(new_path)

        return all_paths

    def shortest_path(self, n1,  n2, path=[], s_p=[]):
        path = path + [n1]
        if n2 == n1:
            return path

        if n1 not in self._graph:
            return
        for key in self._graph[n1]:
            if key not in path:
                s_p = self.shortest_path(key, n2, path)
            if path and len(s_p) < len(path):
                s_p = path

        return s_p

    def dfs_iter(self, root):
        stack = [root]
        visited = []

        while stack:
            node = stack.pop()

            if node not in visited:
                visited.append(node)
                temp = [x for x in self._graph[node] if x not in visited]
                stack.extend(temp)

        return visited

    def dfs_recursive(self, root, visited=[]):
        visited.append(root)

        for vertex in self._graph[root]:
            if vertex not in visited:
                self.dfs_recursive(vertex, visited)

        return visited


inp = [('A', 'B'), ('B', 'C'), ('B', 'D'), ('C', 'D'), ('E', 'F'), ('F', 'C')]
inp1 = [('A', 'B'), ('A', 'C'), ('B', 'A'), ('B', 'D'), ('B', 'E'),
        ('C', 'A'), ('C', 'F'),
        ('D', 'B'), ('E', 'B'), ('E', 'F') , ('F', 'C'), ('F', 'E')]
g = Graphs(inp1)
print g
print g.dfs_iter('A')
print g.dfs_recursive("A")
print g.find_all_paths("C", "F")
print g.shortest_path('A', 'D')
