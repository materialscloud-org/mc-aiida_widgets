"""Module to manage AiiDA codes."""

from subprocess import check_output

import ipywidgets as ipw
from IPython.display import clear_output
from traitlets import Bool, Dict, Instance, Unicode, Union, dlink, link, validate

from aiida.orm import Code, QueryBuilder, User

from aiidalab_widgets_base.utils import predefine_settings, valid_arguments

VALID_AIIDA_CODE_SETUP_ARGUMETNS = {
    'label', 'selected_computer', 'plugin', 'description', 'exec_path', 'prepend_text', 'append_text'
}


def valid_aiidacode_args(arguments):
    return valid_arguments(arguments, VALID_AIIDA_CODE_SETUP_ARGUMETNS)


class CodeDropdown(ipw.VBox):
    """Code selection widget.
    Attributes:
        selected_code(Unicode or Code): Trait that points to the selected Code instance.
            It can be set either to an AiiDA Code instance or to a code label (will
            automatically be replaced by the corresponding Code instance).
            It is linked to the 'value' trait of the `self.dropdown` widget.

        codes(Dict): Trait that contains a dictionary (label => Code instance) for all
            codes found in the AiiDA database for the selected plugin. It is linked
            to the 'options' trait of the `self.dropdown` widget.
    """
    selected_code = Union([Unicode(), Instance(Code)], allow_none=True)
    codes = Dict(allow_none=True)
    disabled = Bool()

    def __init__(self, input_plugin, text='Select code:', path_to_root='../', **kwargs):
        """Dropdown for Codes for one input plugin.

        :param input_plugin: Input plugin of codes to show
        :type input_plugin: str
        :param text: Text to display before dropdown
        :type text: str
        """

        self._description = ipw.Label(
            'Select one of the configured AiiDA codes to execute the calculation or setup a new one.')

        self.input_plugin = input_plugin
        self.output = ipw.Output()

        self.dropdown = ipw.Dropdown(optionsdescription=text)
        link((self, 'codes'), (self.dropdown, 'options'))
        link((self.dropdown, 'value'), (self, 'selected_code'))
        dlink((self, 'disabled'), (self.dropdown, 'disabled'))

        self._btn_refresh = ipw.Button(description="Refresh", layout=ipw.Layout(width="70px"))
        self._btn_refresh.on_click(self.refresh)

        # FOR LATER: use base_url here, when it will be implemented in the appmode.
        self._setup_another = ipw.HTML(value="""<a href={path_to_root}aiidalab-widgets-base/setup_code.ipynb?
                      label={label}&plugin={plugin} target="_blank">Setup new code</a>""".format(
            path_to_root=path_to_root, label=input_plugin, plugin=input_plugin))

        super().__init__(children=[
            self._description,
            ipw.HBox(children=[self.dropdown, self._btn_refresh]),
            self._setup_another,
            self.output],
            **kwargs)

        self.refresh()

    def _get_codes(self):
        """Query the list of available codes."""

        querybuild = QueryBuilder()
        querybuild.append(Code,
                          filters={
                              'attributes.input_plugin': {
                                  '==': self.input_plugin
                              },
                              'extras.hidden': {
                                  "~==": True
                              }
                          },
                          project=['*'])

        # Only codes on computers configured for the current user.
        return {
            self._full_code_label(c[0]): c[0]
            for c in querybuild.all()
            if c[0].computer.is_user_configured(User.objects.get_default())
        }

    @staticmethod
    def _full_code_label(code):
        return "{}@{}".format(code.label, code.computer.name)

    def refresh(self, _=None):
        """Refresh available codes.

        The job of this function is to look in AiiDA database, find available codes and
        put them in the dropdown attribute."""

        with self.output:
            clear_output()
            with self.hold_trait_notifications():
                self.dropdown.options = self._get_codes()

    @validate('selected_code')
    def _validate_selected_code(self, change):
        """If code is provided, set it as it is. If code's name is provided,
        select the code and set it."""
        code = change['value']

        # If code None, set value to None
        if code is None:
            return None

        # Check code by name.
        if isinstance(code, str):
            if code in self.codes:
                return self.codes[code]
            raise KeyError("No code named '{}' found in the AiiDA database.".format(code))

        # Check code by value.
        if isinstance(code, Code):
            label = self._full_code_label(code)
            if label in self.codes:
                return code
            raise ValueError(
                "The code instance '{}' supplied was not found in the AiiDA database. Consider reloading.".format(code))

        # This place will never be reached, because the trait's type is checked.
        return None


class AiiDACodeSetup(ipw.VBox):
    """Class that allows to setup AiiDA code"""

    def __init__(self, **kwargs):
        from aiida.plugins.entry_point import get_entry_point_names
        from aiidalab_widgets_base.computers import ComputerDropdown

        style = {"description_width": "200px"}

        # list of widgets to be displayed

        self._inp_code_label = ipw.Text(description="AiiDA code label:", layout=ipw.Layout(width="500px"), style=style)

        self._computer = ComputerDropdown(layout={'margin': '0px 0px 0px 125px'})

        self._inp_code_description = ipw.Text(placeholder='No description (yet)',
                                              description="Code description:",
                                              layout=ipw.Layout(width="500px"),
                                              style=style)

        self._inp_code_plugin = ipw.Dropdown(options=sorted(get_entry_point_names('aiida.calculations')),
                                             description="Code plugin:",
                                             layout=ipw.Layout(width="500px"),
                                             style=style)

        self._exec_path = ipw.Text(placeholder='/path/to/executable',
                                   description="Absolute path to executable:",
                                   layout=ipw.Layout(width="500px"),
                                   style=style)

        self._prepend_text = ipw.Textarea(placeholder='Text to prepend to each command execution',
                                          description='Prepend text:',
                                          layout=ipw.Layout(width="400px"))

        self._append_text = ipw.Textarea(placeholder='Text to append to each command execution',
                                         description='Append text:',
                                         layout=ipw.Layout(width="400px"))

        self._btn_setup_code = ipw.Button(description="Setup code")
        self._btn_setup_code.on_click(self._setup_code)
        self._setup_code_out = ipw.Output()
        children = [
            ipw.HBox([
                ipw.VBox([
                    self._inp_code_label, self._computer, self._inp_code_plugin, self._inp_code_description,
                    self._exec_path
                ]),
                ipw.VBox([self._prepend_text, self._append_text])
            ]),
            self._btn_setup_code,
            self._setup_code_out,
        ]
        # Check if some settings were already provided
        predefine_settings(self, **kwargs)
        super(AiiDACodeSetup, self).__init__(children, **kwargs)

    def _setup_code(self, change=None):  # pylint: disable=unused-argument
        """Setup an AiiDA code."""
        with self._setup_code_out:
            clear_output()
            if self.label is None:
                print("You did not specify code label")
                return
            if not self.exec_path:
                print("You did not specify absolute path to the executable")
                return
            if self.exists():
                print("Code {}@{} already exists".format(self.label, self.selected_computer.name))
                return
            code = Code(remote_computer_exec=(self.selected_computer, self.exec_path))
            code.label = self.label
            code.description = self.description
            code.set_input_plugin_name(self.plugin)
            code.set_prepend_text(self.prepend_text)
            code.set_append_text(self.append_text)
            code.store()
            code.reveal()
            full_string = "{}@{}".format(self.label, self.selected_computer.name)
            print(check_output(['verdi', 'code', 'show', full_string]).decode('utf-8'))

    def exists(self):
        """Returns True if the code exists, returns False otherwise."""
        from aiida.common import NotExistent, MultipleObjectsError
        try:
            Code.get_from_string("{}@{}".format(self.label, self.selected_computer.name))
            return True
        except MultipleObjectsError:
            return True
        except NotExistent:
            return False

    @property
    def label(self):
        if not self._inp_code_label.value.strip():
            return None
        return self._inp_code_label.value

    @label.setter
    def label(self, label):
        self._inp_code_label.value = label

    @property
    def description(self):
        return self._inp_code_description.value

    @description.setter
    def description(self, description):
        self._inp_code_description.value = description

    @property
    def plugin(self):
        return self._inp_code_plugin.value

    @plugin.setter
    def plugin(self, plugin):
        if plugin in self._inp_code_plugin.options:
            self._inp_code_plugin.value = plugin

    @property
    def exec_path(self):
        return self._exec_path.value

    @exec_path.setter
    def exec_path(self, exec_path):
        self._exec_path.value = exec_path

    @property
    def prepend_text(self):
        return self._prepend_text.value

    @prepend_text.setter
    def prepend_text(self, prepend_text):
        self._prepend_text.value = prepend_text

    @property
    def append_text(self):
        return self._append_text.value

    @append_text.setter
    def append_text(self, append_text):
        self._append_text.value = append_text

    @property
    def selected_computer(self):
        return self._computer.selected_computer

    @selected_computer.setter
    def selected_computer(self, selected_computer):
        self._computer.selected_computer = selected_computer
