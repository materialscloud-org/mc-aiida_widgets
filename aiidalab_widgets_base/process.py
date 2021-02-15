"""Widgets to work with processes."""
# pylint: disable=no-self-use

import os
from inspect import isclass
from time import sleep
import warnings
import pandas as pd
import ipywidgets as ipw
from IPython.display import HTML, Javascript, clear_output, display
from traitlets import Instance, Int, List, Unicode, Union, default, observe, validate

# AiiDA imports.
from aiida.engine import submit, Process, ProcessBuilder
from aiida.orm import CalcFunctionNode, CalcJobNode, Node, ProcessNode, WorkChainNode, WorkFunctionNode, load_node
from aiida.cmdline.utils.common import get_calcjob_report, get_workchain_report, get_process_function_report
from aiida.cmdline.utils.ascii_vis import format_call_graph
from aiida.cmdline.utils.query.calculation import CalculationQueryBuilder
from aiida.common.exceptions import MultipleObjectsError, NotExistent, NotExistentAttributeError

# Local imports.
from .viewers import viewer


def get_running_calcs(process):
    """Takes a process and yeilds running children calculations."""

    # If a process is a running calculation - returning it
    if issubclass(type(process), CalcJobNode) and not process.is_sealed:
        yield process

    # If the process is a running work chain - returning its children
    elif issubclass(type(process), WorkChainNode) and not process.is_sealed:
        for out_link in process.get_outgoing():
            if isinstance(out_link.node, ProcessNode) and not out_link.node.is_sealed:
                yield from get_running_calcs(out_link.node)


class SubmitButtonWidget(ipw.VBox):
    """Submit button class that creates submit button jupyter widget."""
    process = Instance(ProcessNode, allow_none=True)

    def __init__(  # pylint: disable=too-many-arguments
            self,
            process_class,
            inputs_generator=None,
            input_dictionary_function=None,
            description="Submit",
            disable_after_submit=True,
            append_output=False,
            **kwargs):
        """Submit Button widget.

        process_class (Process): Process class to submit.

        inputs_generator (func): Function that returns inputs dictionary or inputs builder.

        input_dictionary_function (DEPRECATED): Function that generates input parameters dictionary.

        description (str): Description written on the submission button.

        disable_after_submit (bool): Whether to disable the button after the process was submitted.

        append_output (bool): Whether to clear widget output for each subsequent submission.
        """

        self.path_to_root = kwargs.get('path_to_root', '../')
        if isclass(process_class) and issubclass(process_class, Process):
            self._process_class = process_class
        else:
            raise ValueError(f"process_class argument must be a sublcass of {Process}, got {process_class}")

        # Handling the deprecation.
        if inputs_generator is None and input_dictionary_function is None:
            raise ValueError("The `inputs_generator` argument must be provided.")
        if inputs_generator and input_dictionary_function:
            raise ValueError("You provided both: `inputs_generator` and `input_dictionary_function` "
                             "arguments. Please provide `inpust_generator` only.")
        if input_dictionary_function:
            inputs_generator = input_dictionary_function
            warnings.warn(("The `input_dictionary_function` argument is deprecated and "
                           "will be removed in the release 1.1 of the aiidalab-widgets-base package. "
                           "Please use the `inputs_generator` argument instead."), DeprecationWarning)

        # Checking if the inputs generator is
        if callable(inputs_generator):
            self.inputs_generator = inputs_generator
        else:
            raise ValueError("The `inputs_generator` argument must be a function that "
                             f"returns input dictionary, got {inputs_generator}")

        self.disable_after_submit = disable_after_submit
        self.append_output = append_output

        self.btn_submit = ipw.Button(description=description, disabled=False)
        self.btn_submit.on_click(self.on_btn_submit_press)
        self.submit_out = ipw.HTML('')
        self._run_after_submitted = []

        super().__init__(children=[self.btn_submit, self.submit_out])

    def on_click(self, function):
        self.btn_submit.on_click(function)

    def on_btn_submit_press(self, _=None):
        """When submit button is pressed."""

        if not self.append_output:
            self.submit_out.value = ''

        inputs = self.inputs_generator()
        if inputs is None:
            if self.append_output:
                self.submit_out.value += "SubmitButtonWidget: did not recieve the process inputs.<br>"
            else:
                self.submit_out.value = "SubmitButtonWidget: did not recieve the process inputs."
        else:
            if self.disable_after_submit:
                self.btn_submit.disabled = True
            if isinstance(inputs, ProcessBuilder):
                self.process = submit(inputs)
            else:
                self.process = submit(self._process_class, **inputs)

            if self.append_output:
                self.submit_out.value += f"""Submitted process {self.process}. Click
                <a href={self.path_to_root}aiidalab-widgets-base/process.ipynb?id={self.process.pk}
                target="_blank">here</a> to follow.<br>"""
            else:
                self.submit_out.value = f"""Submitted process {self.process}. Click
                <a href={self.path_to_root}aiidalab-widgets-base/process.ipynb?id={self.process.pk}
                target="_blank">here</a> to follow."""

            for func in self._run_after_submitted:
                func(self.process)

    def on_submitted(self, function):
        """Run functions after a process has been submitted successfully."""
        self._run_after_submitted.append(function)


class ProcessInputsWidget(ipw.VBox):
    """Widget to select and show process inputs."""

    process = Instance(ProcessNode, allow_none=True)

    def __init__(self, process=None, **kwargs):

        self.output = ipw.Output()
        self.info = ipw.HTML()
        self.inputs = ipw.Dropdown(
            options=[('Select input', '')],
            description='Select input:',
            style={'description_width': 'initial'},
            disabled=False,
        )
        self.process = process
        self.update(process)
        self.inputs.observe(self.show_selected_input, names=['value'])
        super().__init__(
            children=[ipw.HBox([self.inputs, self.info]), self.output],
            **kwargs)

    def show_selected_input(self, change=None):
        """Function that displays process inputs selected in the `inputs` Dropdown widget."""
        with self.output:
            self.info.value = ''
            clear_output()
            if change['new']:
                selected_input = self.process.inputs[change['new']]
                self.info.value = "PK: {}".format(selected_input.id)
                display(viewer(selected_input))

    def update(self, process):
        inputs_list = [(l.title(), l)
                        for l in process.outputs] if process else []
        self.inputs.options = [('Select input', '')] + inputs_list

    @observe('process')
    def _observe_process(self, change):
        process = change['new']
        self.update(process)


class ProcessOutputsWidget(ipw.VBox):
    """Widget to select and show process outputs."""
    process = Instance(ProcessNode, allow_none=True)

    def __init__(self, process=None, **kwargs):
        self.output = ipw.Output()
        self.info = ipw.HTML()
        self.outputs = ipw.Dropdown(
            options=[('Select output', '')],
            label='Select output',
            description='Select outputs:',
            style={'description_width': 'initial'},
            disabled=False,
        )
        self.process = process
        self.update(process)

        self.outputs.observe(self.show_selected_output, names=['value'])
        super().__init__(
            children=[ipw.HBox([self.outputs, self.info]), self.output],
            **kwargs)

    def show_selected_output(self, change=None):
        """Function that displays process output selected in the `outputs` Dropdown widget."""
        with self.output:
            self.info.value = ''
            clear_output()
            if change['new']:
                selected_output = self.process.outputs[change['new']]
                self.info.value = "PK: {}".format(selected_output.id)
                display(viewer(selected_output))

    def update(self, process):
        outputs_list = [(l.title(), l)
                        for l in process.outputs] if process else []
        self.outputs.options = [('Select output', '')] + outputs_list

    @observe('process')
    def _observe_process(self, change):
        process = change['new']
        self.update(process)


class ProcessFollowerWidget(ipw.VBox):
    """A Widget that follows a process until finished."""
    process = Instance(ProcessNode, allow_none=True)

    def __init__(self, process=None, followers=None, update_interval=0.1, path_to_root='../', **kwargs):
        """Initiate all the followers."""
        self.process = process
        self._run_after_completed = []
        self.update_interval = update_interval
        self.followers = []
        if followers is not None:
            for follower in followers:
                follower.process = self.process
                follower.path_to_root = path_to_root
                self.followers.append(ipw.VBox([
                    ipw.HTML("<h2><b>{}</b></h2>".format(follower.title)),
                    follower,
                ]))
        self.update()
        self.output = ipw.HTML()
        super().__init__(children=[self.output] + self.followers, **kwargs)

    def update(self):
        for follower in self.followers:
            follower.children[1].update()

    def _follow(self):
        """Periodically update all followers while the process is running."""
        while not self.process.is_sealed:
            self.update()
            sleep(self.update_interval)
        self.update()  # Update the state for the last time to be 100% sure.

        # Call functions to be run after the process is completed.
        for func in self._run_after_completed:
            func(self.process)

    def follow(self, detach=False):
        """Initiate following the process with or without blocking."""
        if self.process is None:
            self.output.value = """<font color="red"> ProcessFollowerWidget: process
            is set to 'None', nothing to follow. </font>"""
            return
        self.output.value = ''

        if detach:
            import threading
            update_state = threading.Thread(target=self._follow)
            update_state.start()
        else:
            self._follow()

    def on_completed(self, function):
        """Run functions after a process has been completed."""
        self._run_after_completed.append(function)


class ProcessReportWidget(ipw.HTML):
    """Widget that shows process report."""
    process = Instance(ProcessNode, allow_none=True)

    def __init__(self, title="Process Report", **kwargs):
        self.title = title
        self.max_depth = None
        self.indent_size = 2
        self.levelname = 'REPORT'
        self.update()
        super().__init__(**kwargs)

    def update(self):
        """Update report that is shown."""
        if self.process is None:
            return

        if isinstance(self.process, CalcJobNode):
            string = get_calcjob_report(self.process)
        elif isinstance(self.process, WorkChainNode):
            string = get_workchain_report(self.process, self.levelname, self.indent_size, self.max_depth)
        elif isinstance(self.process, (CalcFunctionNode, WorkFunctionNode)):
            string = get_process_function_report(self.process)
        else:
            string = 'Nothing to show for node type {}'.format(self.process.__class__)
        self.value = string.replace('\n', '<br/>')


class ProcessCallStackWidget(ipw.HTML):
    """Widget that shows process call stack."""
    process = Instance(ProcessNode, allow_none=True)

    def __init__(self, title="Process Call Stack", path_to_root='../', **kwargs):
        self.title = title
        self.path_to_root = path_to_root
        self.update()
        super().__init__(**kwargs)

    def update(self):
        """Update the call stack that is shown."""
        if self.process is None:
            return
        string = format_call_graph(self.process, info_fn=self.calc_info)
        self.value = string.replace('\n', '<br/>').replace(' ', '&nbsp;').replace('#space#', ' ')

    def calc_info(self, node):
        """Return a string with the summary of the state of a CalculationNode."""

        if not isinstance(node, ProcessNode):
            raise TypeError('Unknown type: {}'.format(type(node)))

        process_state = node.process_state.value.capitalize()
        pk = """<a#space#href={0}aiidalab-widgets-base/process.ipynb?id={1}#space#target="_blank">{1}</a>""".format(
            self.path_to_root, node.pk)

        if node.exit_status is not None:
            string = '{}<{}> {} [{}]'.format(node.process_label, pk, process_state, node.exit_status)
        else:
            string = '{}<{}> {}'.format(node.process_label, pk, process_state)

        if isinstance(node, WorkChainNode) and node.stepper_state_info:
            string += ' [{}]'.format(node.stepper_state_info)
        return string


class ProgressBarWidget(ipw.VBox):
    """A bar showing the proggress of a process."""
    process = Instance(ProcessNode, allow_none=True)

    def __init__(self, title="Progress Bar", **kwargs):
        """Initialize ProgressBarWidget."""

        self.title = title
        self.correspondance = {
            "created": 0,
            "running": 1,
            "waiting": 1,
            "killed": 2,
            "excepted": 2,
            "finished": 2,
        }
        self.progress_bar = ipw.IntProgress(
            value=0,
            min=0,
            max=2,
            step=1,
            description='Progress:',
            bar_style='warning',  # 'success', 'info', 'warning', 'danger' or ''
            orientation='horizontal',
            layout={'width': '800px'})
        self.state = ipw.HTML(description="Calculation state:", value='Created', style={'description_width': 'initial'})
        super().__init__(children=[self.progress_bar, self.state], **kwargs)

    def update(self):
        """Update the bar."""
        if self.process is None:
            return
        self.progress_bar.value = self.correspondance[self.current_state]
        if self.current_state == 'finished':
            self.progress_bar.bar_style = 'success'
        elif self.current_state in ["killed", "excepted"]:
            self.progress_bar.bar_style = 'danger'
        else:
            self.progress_bar.bar_style = 'info'
        self.state.value = self.current_state.capitalize()

    @property
    def current_state(self):
        return self.process.process_state.value


class CalcJobOutputWidget(ipw.Textarea):
    """Output of a calculation."""
    calculation = Instance(CalcJobNode, allow_none=True)

    def __init__(self, **kwargs):
        default_params = {
            "value": "",
            "placeholder": "Calculation output will appear here",
            "description": "Calculation output:",
            "layout": {
                'width': "900px",
                'height': '300px'
            },
            "disabled": False,
            "style": {
                'description_width': 'initial'
            }
        }
        default_params.update(kwargs)
        self.output = []

        # Hack to make font monospace. As far as I am aware, currently there are no better ways.
        display(HTML("<style>textarea, input { font-family: monospace; }</style>"))

        super().__init__(**default_params)

    @observe('calculation')
    def _change_calculation(self, _=None):
        """Reset things if the observed calculation has changed."""
        self.output = []
        self.value = ''

    def update(self):
        """Update the displayed output and scroll to its end.

        NOTE: when this widgets is called by ProcessFollowerWidget in non-blocking manner
        the auto-scrolling won't work. There used to be a function for the Textarea widget,
        but it didn't work properly and got removed. For more information please visit:
        https://github.com/jupyter-widgets/ipywidgets/issues/1815"""

        if self.calculation is None:
            return

        try:
            output_file_path = os.path.join(self.calculation.outputs.remote_folder.get_remote_path(),
                                            self.calculation.attributes['output_filename'])
        except KeyError:
            self.placeholder = "The `output_filename` attribute is not set for " \
            f"{self.calculation.process_class}. Nothing to show."
        except NotExistentAttributeError:
            self.placeholder = "The object `remote_folder` was not found among the process outputs. " \
            "Nothing to show."
        else:
            if os.path.exists(output_file_path):
                with open(output_file_path) as fobj:
                    difference = fobj.readlines()[len(self.output):-1]  # Only adding the difference
                    self.output += difference
                    self.value += ''.join(difference)

        # Auto scroll down. Doesn't work in detached mode.
        # Also a hack as it is applied to all the textareas
        display(
            Javascript("""
            $('textarea').each(function(){
                // get the id
                var id_value = $(this).attr('id');

                if (typeof id_value !== 'undefined') {
                    // the variable is defined
                    var textarea = document.getElementById(id_value);
                    textarea.scrollTop = textarea.scrollHeight;
                }   
            });"""))


class RunningCalcJobOutputWidget(ipw.VBox):
    """Show an output of selected running child calculation."""
    process = Instance(ProcessNode, allow_none=True)

    def __init__(self, title="Running Job Output", **kwargs):
        self.title = title
        self.selection = ipw.Dropdown(description="Select calculation:",
                                      options={p.id: p for p in get_running_calcs(self.process)},
                                      style={'description_width': 'initial'})
        self.output = CalcJobOutputWidget()
        self.update()
        super().__init__(children=[self.selection, self.output], **kwargs)

    def update(self):
        """Update the displayed output."""
        if self.process is None:
            return
        with self.hold_trait_notifications():
            old_label = self.selection.label
            self.selection.options = {str(p.id): p for p in get_running_calcs(self.process)}
            # If the selection remains the same.
            if old_label in self.selection.options:
                self.label = old_label  # After changing options trait, the label and value traits might change as well.
            # If selection has changed
            else:
                self.output.calculation = self.selection.value
        self.output.update()


class ProcessListWidget(ipw.VBox):
    """List of AiiDA processes.

        past_days (int): Sumulations that were submitted in the last `past_days`.

        incoming_node (int, str, Node): Trait that takes node id or uuid and returns the node that must
        be among the input nodes of the process of interest.

        outgoing_node (int, str, Node): Trait that takes node id or uuid and returns the node that must
        be among the output nodes of the process of interest.

        process_states (list): List of allowed process states.

        process_label (str): Show process states of type `process_label`.

        description_contains (str): string that should be present in the description of a process node.

    """
    past_days = Int(7)
    incoming_node = Union([Int(), Unicode(), Instance(Node)], allow_none=True)
    outgoing_node = Union([Int(), Unicode(), Instance(Node)], allow_none=True)
    process_states = List()
    process_label = Unicode(allow_none=True)
    description_contains = Unicode(allow_none=True)

    def __init__(self, path_to_root='../', **kwargs):
        self.path_to_root = path_to_root
        self.table = ipw.HTML()
        pd.set_option('max_colwidth', 40)
        self.output = ipw.HTML()
        update_button = ipw.Button(description="Update now")
        update_button.on_click(self.update)
        self.update()
        super().__init__(children=[ipw.HBox([self.output, update_button]), self.table], **kwargs)

    def update(self, _=None):
        """Perform the query."""
        # Here we are defining properties of 'df' class (specified while exporting pandas table into html).
        # Since the exported object is nothing more than HTML table, all 'standard' HTML table settings
        # can be applied to it as well.
        # For more information on how to controle the table appearance please visit:
        # https://css-tricks.com/complete-guide-table-element/
        self.table.value = '''
        <style>
            .df { border: none; }
            .df tbody tr:nth-child(odd) { background-color: #e5e7e9; }
            .df tbody tr:nth-child(odd):hover { background-color:   #f5b7b1; }
            .df tbody tr:nth-child(even):hover { background-color:  #f5b7b1; }
            .df tbody td { min-width: 150px; text-align: center; border: none }
            .df th { text-align: center; border: none;  border-bottom: 1px solid black;}
        </style>
        '''
        builder = CalculationQueryBuilder()
        filters = builder.get_filters(all_entries=False,
                                      process_state=self.process_states,
                                      process_label=self.process_label,
                                      exit_status=None,
                                      failed=None)
        relationships = {}
        if self.incoming_node:
            relationships = {**relationships, **{'with_outgoing': self.incoming_node}}

        if self.outgoing_node:
            relationships = {**relationships, **{'with_incoming': self.outgoing_node}}

        query_set = builder.get_query_set(
            filters=filters,
            past_days=None if self.past_days < 0 else self.past_days,
            order_by={'ctime': 'desc'},
            relationships=relationships,
        )
        projected = builder.get_projected(
            query_set, projections=['pk', 'ctime', 'process_label', 'state', 'process_status', 'description'])
        dataf = pd.DataFrame(projected[1:], columns=projected[0])

        # Keep only process that contain the requested string in the description.
        if self.description_contains:
            dataf = dataf[dataf.Description.str.contains(self.description_contains)]

        self.output.value = "{} processes shown".format(len(dataf))

        # Add HTML links.
        dataf['PK'] = dataf['PK'].apply(
            lambda x: """<a href={0}aiidalab-widgets-base/process.ipynb?id={1} target="_blank">{1}</a>""".format(
                self.path_to_root, x))
        self.table.value += dataf.to_html(classes='df', escape=False, index=False)

    @validate('incoming_node')
    def _validate_incoming_node(self, provided):
        """Validate incoming node. The function load_node takes care of managing ids and uuids."""
        if provided['value']:
            try:
                return load_node(provided['value'])
            except (MultipleObjectsError, NotExistent):
                return None
        return None

    @validate('outgoing_node')
    def _validate_outgoing_node(self, provided):
        """Validate outgoing node. The function load_node takes care of managing ids and uuids."""
        if provided['value']:
            try:
                return load_node(provided['value'])
            except (MultipleObjectsError, NotExistent):
                return None
        return None

    @default('process_label')
    def _default_process_label(self):
        return None

    @validate('process_label')
    def _validate_process_label(self, provided):
        if provided['value']:
            return provided['value']
        return None

    def _follow(self, update_interval):
        while True:
            self.update()
            sleep(update_interval)

    def start_autoupdate(self, update_interval=10):
        import threading
        update_state = threading.Thread(target=self._follow, args=(update_interval,))
        update_state.start()
