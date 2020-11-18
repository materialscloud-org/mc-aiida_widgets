"""Module to manage AiiDA codes."""

from subprocess import check_output

import ipywidgets as ipw
from IPython.display import clear_output
from traitlets import Bool, Dict, Instance, Unicode, Union, dlink, link, validate

from aiida.orm import Code, QueryBuilder, User
from aiida.plugins.entry_point import get_entry_point_names
from aiidalab_widgets_base.computers import ComputerDropdown


class CodeDropdown(ipw.VBox):
    """Code selection widget.
    Attributes:

    selected_code(Unicode or Code): Trait that points to the selected Code instance.
    It can be set either to an AiiDA Code instance or to a code label (will automatically
    be replaced by the corresponding Code instance). It is linked to the 'value' trait of
    the `self.dropdown` widget.

    codes(Dict): Trait that contains a dictionary (label => Code instance) for all
    codes found in the AiiDA database for the selected plugin. It is linked
    to the 'options' trait of the `self.dropdown` widget.

    allow_hidden_codes(Bool): Trait that defines whether to show hidden codes or not.

    allow_disabled_computers(Bool): Trait that defines whether to show codes on disabled
    computers.
    """
    selected_code = Union([Unicode(), Instance(Code)], allow_none=True)
    codes = Dict(allow_none=True)
    allow_hidden_codes = Bool(False)
    allow_disabled_computers = Bool(False)

    def __init__(self, input_plugin, description='Select code:', path_to_root='../', **kwargs):
        """Dropdown for Codes for one input plugin.

        input_plugin (str): Input plugin of codes to show.

        description (str): Description to display before the dropdown.
        """
        self.output = ipw.Output()

        self.input_plugin = input_plugin

        self.dropdown = ipw.Dropdown(description=description, disabled=True, value=None)
        link((self, 'codes'), (self.dropdown, 'options'))
        link((self.dropdown, 'value'), (self, 'selected_code'))

        btn_refresh = ipw.Button(description="Refresh", layout=ipw.Layout(width="70px"))
        btn_refresh.on_click(self.refresh)

        self.observe(self.refresh, names=['allow_disabled_computers', 'allow_hidden_codes'])

        # Prepare URL parameters for the code setup.
        setup_code_params = {
            "label": input_plugin,
            "plugin": input_plugin,
        }

        for key, value in kwargs.pop('setup_code_params', {}).items():
            setup_code_params[key] = value

        ## For later: use base_url here, when it will be implemented in the appmode.
        url_string = f"<a href={path_to_root}aiidalab-widgets-base/setup_code.ipynb?"
        url_string += "&".join([f"{k}={v}".replace(' ', '%20') for k, v in setup_code_params.items()])
        url_string += ' target="_blank">Setup new code</a>'

        children = [ipw.HBox([self.dropdown, btn_refresh, ipw.HTML(value=url_string)]), self.output]

        super().__init__(children=children, **kwargs)

        self.refresh()

    def _get_codes(self):
        """Query the list of available codes."""

        user = User.objects.get_default()

        return {
            self._full_code_label(c[0]): c[0]
            for c in QueryBuilder().append(Code, filters={
                'attributes.input_plugin': self.input_plugin
            }).all()
            if c[0].computer.is_user_configured(user) and (self.allow_hidden_codes or not c[0].hidden) and
            (self.allow_disabled_computers or c[0].computer.is_user_enabled(user))
        }

    @staticmethod
    def _full_code_label(code):
        return f"{code.label}@{code.computer.name}"

    def refresh(self, _=None):
        """Refresh available codes.

        The job of this function is to look in AiiDA database, find available codes and
        put them in the dropdown attribute."""

        with self.output:
            clear_output()
            with self.hold_trait_notifications():
                self.dropdown.options = self._get_codes()
            if not self.dropdown.options:
                print("No codes found for input plugin '{self.input_plugin}'.")
                self.dropdown.disabled = True
            else:
                self.dropdown.disabled = False
            self.dropdown.value = None

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
            raise KeyError(f"No code named '{code}' found in the AiiDA database.")

        # Check code by value.
        if isinstance(code, Code):
            label = self._full_code_label(code)
            if label in self.codes:
                return code
            raise ValueError(
                f"The code instance '{code}' supplied was not found in the AiiDA database. Consider reloading.")

        # This place will never be reached, because the trait's type is checked.
        return None


class AiiDACodeSetup(ipw.VBox):
    """Class that allows to setup AiiDA code"""
    label = Unicode()
    computer = Unicode()
    input_plugin = Unicode()
    description = Unicode()
    remote_abs_path = Unicode()
    prepend_text = Unicode()
    append_text = Unicode()

    def __init__(self, **kwargs):

        style = {"description_width": "200px"}

        # Code label.
        inp_label = ipw.Text(description="AiiDA code label:", layout=ipw.Layout(width="500px"), style=style)
        link((inp_label, 'value'), (self, 'label'))

        # Computer on which the code is installed.
        inp_computer = ComputerDropdown(layout={'margin': '0px 0px 0px 125px'})
        dlink((inp_computer, 'label'), (self, 'computer'))
        dlink((self, 'computer'), (inp_computer, 'selected_computer'))

        # Code plugin.
        inp_code_plugin = ipw.Dropdown(options=sorted(get_entry_point_names('aiida.calculations')),
                                       description="Code plugin:",
                                       layout=ipw.Layout(width="500px"),
                                       style=style)
        link((inp_code_plugin, 'value'), (self, 'input_plugin'))

        # Code description.
        inp_description = ipw.Text(placeholder='No description (yet)',
                                   description="Code description:",
                                   layout=ipw.Layout(width="500px"),
                                   style=style)
        link((inp_description, 'value'), (self, 'description'))

        inp_abs_path = ipw.Text(placeholder='/path/to/executable',
                                description="Absolute path to executable:",
                                layout=ipw.Layout(width="500px"),
                                style=style)
        link((inp_abs_path, 'value'), (self, 'remote_abs_path'))

        inp_prepend_text = ipw.Textarea(placeholder='Text to prepend to each command execution',
                                        description='Prepend text:',
                                        layout=ipw.Layout(width="400px"))
        link((inp_prepend_text, 'value'), (self, 'prepend_text'))

        inp_append_text = ipw.Textarea(placeholder='Text to append to each command execution',
                                       description='Append text:',
                                       layout=ipw.Layout(width="400px"))
        link((inp_append_text, 'value'), (self, 'append_text'))

        btn_setup_code = ipw.Button(description="Setup code")
        btn_setup_code.on_click(self._setup_code)
        self._setup_code_out = ipw.Output()
        children = [
            ipw.HBox([
                ipw.VBox([inp_label, inp_computer, inp_code_plugin, inp_description, inp_abs_path]),
                ipw.VBox([inp_prepend_text, inp_append_text])
            ]),
            btn_setup_code,
            self._setup_code_out,
        ]
        super(AiiDACodeSetup, self).__init__(children, **kwargs)

    def _setup_code(self, _=None):
        """Setup an AiiDA code."""
        with self._setup_code_out:
            clear_output()
            if self.label is None:
                print("You did not specify code label")
                return
            if not self.remote_abs_path:
                print("You did not specify absolute path to the executable")
                return
            if self.exists():
                print(f"Code {self.label}@{self.computer.name} already exists")
                return
            code = Code(remote_computer_exec=(self.computer, self.remote_abs_path))
            code.label = self.label
            code.description = self.description
            code.set_input_plugin_name(self.input_plugin)
            code.set_prepend_text(self.prepend_text)
            code.set_append_text(self.append_text)
            code.store()
            code.reveal()
            full_string = f"{self.label}@{self.computer.name}"
            print(check_output(['verdi', 'code', 'show', full_string]).decode('utf-8'))

    def exists(self):
        """Returns True if the code exists, returns False otherwise."""
        from aiida.common import NotExistent, MultipleObjectsError
        try:
            Code.get_from_string(f"{self.label}@{self.computer.name}")
            return True
        except MultipleObjectsError:
            return True
        except NotExistent:
            return False
