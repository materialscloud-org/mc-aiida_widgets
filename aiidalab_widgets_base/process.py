"""Widgets to work with processes."""
from __future__ import absolute_import
from __future__ import print_function

import os
from ipywidgets import Textarea, VBox


def get_running_calcs(process):
    """Takes a process and returns a list of running calculations. The running calculations
    can be either the process itself or its running children."""

    from aiida.orm import CalcJobNode, ProcessNode, WorkChainNode

    if process.is_sealed:
        pass  # nothing to yield
    elif isinstance(process, CalcJobNode):
        yield process
    elif isinstance(process, WorkChainNode):
        for link in process.get_outgoing():
            if isinstance(link.node, ProcessNode) and not link.node.is_sealed:
                yield from get_running_calcs(link.node)


class SubmitButtonWidget(VBox):
    """Submit button class that creates submit button jupyter widget."""

    def __init__(self, process, widgets_values):
        """Submit Button
        :process: work chain to run
        :param_funtion: the function that generates input parameters dictionary
        """
        from ipywidgets import Button, Output

        self.process = None
        self._process_class = process
        self.widgets_values = widgets_values
        self.btn_submit = Button(description="Submit", disabled=False)
        self.btn_submit.on_click(self.on_btn_submit_press)
        self.submit_out = Output()
        children = [
            self.btn_submit,
            self.submit_out,
        ]
        super(SubmitButtonWidget, self).__init__(children=children)

    def on_click(self, function):
        self.btn_submit.on_click(function)

    def on_btn_submit_press(self, _):
        """When submit button is pressed."""
        from IPython.display import clear_output
        from aiida.engine import submit

        with self.submit_out:
            clear_output()
            self.btn_submit.disabled = True
            input_dict = self.widgets_values()
            self.process = submit(self._process_class, **input_dict)
            print("Submitted process {}".format(self.process))
            return


class ProcessFollowerWidget(VBox):
    """A Widget that follows a process until finished."""

    def __init__(self, process, followers=None, update_interval=0.1, **kwargs):
        """Initiate all the followers."""
        from aiida.orm import ProcessNode

        if not isinstance(process, ProcessNode):
            raise TypeError("Expecting an object of type {}, got {}".format(ProcessNode, type(process)))
        self.process = process
        self.update_interval = update_interval
        self.followers = []
        if followers is not None:
            for follower in followers:
                self.followers.append(follower(process=process))
        self.update()
        super(ProcessFollowerWidget, self).__init__(children=self.followers, **kwargs)

    def update(self):
        for follower in self.followers:
            follower.update()

    def _follow(self):
        """The loop that will update all the followers untill the process is running."""
        from time import sleep
        while not self.process.is_sealed:
            self.update()
            sleep(self.update_interval)
        self.update()  # update the state for the last time to be 100% sure

    def follow(self, detach=False):
        """Follow the process in blocking or non-blocking manner."""
        if detach:
            import threading
            update_state = threading.Thread(target=self._follow)
            update_state.start()
        else:
            self._follow()


class ProgressBarWidget(VBox):
    """A bar showing the proggress of a process."""

    def __init__(self, process=None, **kwargs):
        from ipywidgets import HTML, IntProgress, Layout

        self.process = process
        self.correspondance = {
            "created": 0,
            "running": 1,
            "waiting": 1,
            "killed": 2,
            "excepted": 2,
            "finished": 2,
        }
        self.bar = IntProgress(  # pylint: disable=blacklisted-name
            value=0,
            min=0,
            max=2,
            step=1,
            description='Progress:',
            bar_style='warning',  # 'success', 'info', 'warning', 'danger' or ''
            orientation='horizontal',
            layout=Layout(width="800px"))
        self.state = HTML(description="Calculation state:", value='Created', style={'description_width': 'initial'})
        children = [self.bar, self.state]
        super(ProgressBarWidget, self).__init__(children=children, **kwargs)

    def update(self):
        """Update the bar."""
        self.bar.value = self.correspondance[self.current_state]
        if self.current_state == 'finished':
            self.bar.bar_style = 'success'
        elif self.current_state in ["killed", "excepted"]:
            self.bar.bar_style = 'danger'
        else:
            self.bar.bar_style = 'info'
        self.state.value = self.current_state.capitalize()

    @property
    def current_state(self):
        return self.process.process_state.value


class RunningCalcJobOutputWidget(Textarea):
    """Output of a currently running calculation or one of work chain's running child."""

    def __init__(self, process, **kwargs):
        self.main_process = process
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
        self.previous_calc_id = 0
        self.output = []
        super(RunningCalcJobOutputWidget, self).__init__(**default_params)

    def update(self):
        """Update the displayed output."""
        for calc in get_running_calcs(self.main_process):
            if calc.id == self.previous_calc_id:
                break
            else:
                self.output = []
                self.previous_calc_id = calc.id
                self.value = ''
            if 'remote_folder' in calc.outputs:
                f_path = os.path.join(calc.outputs.remote_folder.get_remote_path(), calc.attributes['output_filename'])
                if os.path.exists(f_path):
                    with open(f_path) as fobj:
                        self.output += fobj.readlines()[len(self.output):-1]
                        self.value = ''.join(self.output)
