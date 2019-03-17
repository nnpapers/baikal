import warnings

from baikal.core.data import is_data_list
from baikal.core.digraph import DiGraph
from baikal.core.step import Step
from baikal.core.utils import listify


class Model(Step):
    def __init__(self, inputs, outputs, name=None):
        super(Step, self).__init__(name=name)

        inputs = listify(inputs)
        outputs = listify(outputs)

        if not is_data_list(inputs) or not is_data_list(outputs):
            raise ValueError('inputs and outputs must be of type Data.')

        self.inputs = inputs
        self.outputs = outputs
        self._graph = self._build_graph()
        self._steps = self._get_required_steps()

    def _build_graph(self):
        # Model uses the DiGraph data structure to store and operate on its Data and Steps.
        graph = DiGraph()

        # Add nodes (steps)
        def collect_steps_from(output):
            parent_step = output.step
            graph.add_node(parent_step)
            for input in parent_step.inputs:
                collect_steps_from(input)

        for output in self.outputs:
            collect_steps_from(output)

        # Add edges (data)
        for step in graph:
            for input in step.inputs:
                graph.add_edge(input.step, step)

        return graph

    def _get_required_steps(self):
        all_steps_sorted = self._graph.topological_sort()  # Fail early if graph is acyclic

        # Backtrack from outputs until inputs to get the necessary steps. That is,
        # find the ancestors of the nodes that provide the specified outputs.
        # Raise an error if there is an ancestor whose input is not in the specified inputs.
        # We assume a DAG (guaranteed by success of topological_sort).

        all_required_steps = set()
        inputs_found = []

        # Depth-first search
        def backtrack(output):
            required_steps = set()

            if output in self.inputs:
                inputs_found.append(output)
                return required_steps

            parent_step = output.step
            if parent_step in all_required_steps:
                return required_steps

            required_steps = {parent_step}
            for input in parent_step.inputs:
                required_steps |= backtrack(input)
            return required_steps

        for output in self.outputs:
            all_required_steps |= backtrack(output)

        # Check for any unused inputs
        for input in self.inputs:
            if input not in inputs_found:
                warnings.warn(
                    'Input {} was provided but it is not required to compute the specified outputs.'.format(input.name),
                    RuntimeWarning)

        # Check for missing inputs
        missing_inputs = []
        for step in all_required_steps:
            if self._graph.in_degree(step) == 0:
                missing_inputs.extend(step.outputs)

        if missing_inputs:
            raise ValueError('The following inputs are required but were not specified:\n'
                             '{}'.format(','.join([input.name for input in missing_inputs])))

        return [step for step in all_steps_sorted if step in all_required_steps]

    def fit(self, input_data, target_data=None):
        # TODO: target_data must match the number of inputs.
        # For outputs that do not require target data their corresponding list element must be None.
        # TODO: add extra_targets keyword argument
        # TODO: Add **fit_params argument (like sklearn's Pipeline.fit)
        # TODO: Consider using joblib's Parallel and Memory classes to parallelize and cache computations
        # In graph parlance, the 'parallelizable' paths of a graph are called 'disjoint paths'
        # https://stackoverflow.com/questions/37633941/get-list-of-parallel-paths-in-a-directed-graph

        cache = dict()  # keys: Data instances, values: actual data (e.g. numpy arrays)

        input_data = listify(input_data)
        if len(input_data) != len(self.inputs):
            raise ValueError('The number of training data arrays does not match the number of inputs!')
        cache.update(zip(self.inputs, input_data))

        if target_data is not None:
            # FIXME: This should check only the outputs that require target_data
            target_data = listify(target_data)
            if len(target_data) != len(self.outputs):
                raise ValueError('The number of target data arrays does not match the number of outputs!')
            cache.update(zip(self.outputs, target_data))

        # cache.update(extra_targets)

        for step in self._steps:
            # 1) Fit phase
            Xs = [cache[i] for i in step.inputs]
            ys = [cache[o] for o in step.outputs if o in cache]
            step.fit(*Xs, *ys)

            # 2) predict/transform phase
            # TODO: Some regressors have extra options in their predict method, and they return a tuple of arrays.
            # https://scikit-learn.org/stable/glossary.html#term-predict
            if hasattr(step, 'predict'):
                output_data = step.predict(*Xs)
            elif hasattr(step, 'transform'):
                output_data = step.transform(*Xs)
            else:
                raise TypeError('{} does not implement predict or transform!'.format(step.name))

            # TODO: Raise warning if computed output is already in cache.
            # This happens when recomputing a step that had some of its outputs already passed in the inputs.
            cache.update(zip(step.outputs, listify(output_data)))

    def predict(self, input_data):
        cache = dict()  # keys: Data instances, values: actual data (e.g. numpy arrays)

        input_data = listify(input_data)
        if len(input_data) != len(self.inputs):
            raise ValueError('The number of training data arrays does not match the number of inputs!')
        cache.update(zip(self.inputs, input_data))

        for step in self._steps:
            # TODO: Some regressors have extra options in their predict method, and they return a tuple of arrays.
            # https://scikit-learn.org/stable/glossary.html#term-predict
            Xs = [cache[i] for i in step.inputs]
            if hasattr(step, 'predict'):
                output_data = step.predict(*Xs)
            elif hasattr(step, 'transform'):
                output_data = step.transform(*Xs)
            else:
                raise TypeError('{} does not implement predict or transform!'.format(step.name))

            # TODO: Raise warning if computed output is already in cache.
            # This happens when recomputing a step that had some of its outputs already passed in the inputs.
            cache.update(zip(step.outputs, listify(output_data)))

        output_data = [cache[o] for o in self.outputs]
        if len(output_data) == 1:
            return output_data[0]
        else:
            return output_data

    # TODO: Implement build_output_shapes method.
    # TODO: Override __call__ method
    # predict: inputs (outputs) can be either: a list of arrays
    # (interpreted as 1to1 correspondence with inputs (outputs) passed at __init__),
    # or a dictionary keyed by Data instances or their names with array values. We need input normalization for this.
    # Also, check that all of requested output keys exist in the Model (sub)graph (not the parent graph!)

    @property
    def graph(self):
        return self._graph
