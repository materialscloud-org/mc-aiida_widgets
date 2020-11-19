"""All functionality needed to setup a computer."""

import os
from os import path
from copy import copy
from subprocess import check_output, call

import pexpect
import shortuuid
import ipywidgets as ipw
from IPython.display import clear_output
from traitlets import Bool, Dict, Instance, Int, Unicode, Union, link, validate

from aiida.common import NotExistent
from aiida.orm import Computer, QueryBuilder, User

from aiida.transports.plugins.ssh import parse_sshconfig

STYLE = {"description_width": "200px"}


class SshComputerSetup(ipw.VBox):
    """Setup password-free access to a computer."""
    setup_counter = Int(0)  # Traitlet to inform other widgets about changes
    hostname = Unicode()
    port = Union([Unicode(), Int()])
    use_proxy = Bool()
    username = Unicode()
    proxy_hostname = Unicode()
    proxy_username = Unicode()

    def __init__(self, **kwargs):
        computer_image = ipw.HTML('<img width="200px" src="./miscellaneous/images/computer.png">')

        # Username.
        inp_username = ipw.Text(description="SSH username:", layout=ipw.Layout(width="350px"), style=STYLE)
        link((inp_username, 'value'), (self, 'username'))

        # Port.
        inp_port = ipw.IntText(description="SSH port:", value=22, layout=ipw.Layout(width="350px"), style=STYLE)
        link((inp_port, 'value'), (self, 'port'))

        # Hostname.
        inp_computer_hostname = ipw.Text(description="Computer hostname:",
                                         layout=ipw.Layout(width="350px"),
                                         style=STYLE)
        link((inp_computer_hostname, 'value'), (self, 'hostname'))

        # Upload private key directly.
        self._inp_password = ipw.Password(description="SSH password:",
                                          layout=ipw.Layout(width="150px"),
                                          style=STYLE,
                                          disabled=False)
        self._inp_private_key = ipw.FileUpload(accept='',
                                               layout=ipw.Layout(width="350px"),
                                               style=STYLE,
                                               description='Private key',
                                               multiple=False,
                                               disabled=True)
        self._verification_mode = ipw.Dropdown(options=['password', 'private_key'],
                                               layout=ipw.Layout(width="350px"),
                                               style=STYLE,
                                               value='password',
                                               description='verification mode:',
                                               disabled=False)
        self._verification_mode.observe(self.on_use_verification_mode_change, names='value')

        # Proxy ssh settings.
        inp_use_proxy = ipw.Checkbox(value=False, description='Use proxy')
        inp_use_proxy.observe(self.on_use_proxy_change, names='value')
        link((inp_use_proxy, 'value'), (self, 'use_proxy'))

        inp_proxy_hostname = ipw.Text(description="Proxy server address:",
                                      layout=ipw.Layout(width="350px"),
                                      style=STYLE)
        link((inp_proxy_hostname, 'value'), (self, 'proxy_hostname'))

        self._use_diff_proxy_username = ipw.Checkbox(value=False,
                                                     description='Use different username and password',
                                                     layout={'width': 'initial'})
        self._use_diff_proxy_username.observe(self.on_use_diff_proxy_username_change, names='value')
        inp_proxy_username = ipw.Text(value='',
                                      description="Proxy server username:",
                                      layout=ipw.Layout(width="350px"),
                                      style=STYLE)
        link((inp_proxy_username, 'value'), (self, 'proxy_username'))

        self._inp_proxy_password = ipw.Password(value='',
                                                description="Proxy server password:",
                                                layout=ipw.Layout(width="138px"),
                                                style=STYLE)

        # Setup ssh button and output.
        btn_setup_ssh = ipw.Button(description="Setup ssh")
        btn_setup_ssh.on_click(self.on_setup_ssh)
        self._setup_ssh_out = ipw.Output()

        # Defining widgets positions.
        computer_ssh_box = ipw.VBox([
            inp_computer_hostname, inp_port, inp_username, self._verification_mode, self._inp_password,
            self._inp_private_key, inp_use_proxy
        ],
                                    layout=ipw.Layout(width="400px"))
        self._proxy_user_password_box = ipw.VBox([inp_proxy_username, self._inp_proxy_password],
                                                 layout={'visibility': 'hidden'})
        self._proxy_ssh_box = ipw.VBox(
            [inp_proxy_hostname, self._use_diff_proxy_username, self._proxy_user_password_box],
            layout={
                'visibility': 'hidden',
                'width': '400px'
            })

        children = [
            ipw.HBox([computer_image, computer_ssh_box, self._proxy_ssh_box]), btn_setup_ssh, self._setup_ssh_out
        ]
        super(SshComputerSetup, self).__init__(children, **kwargs)

    @staticmethod
    def _ssh_keygen():
        """Generate ssh key pair."""
        fname = path.expanduser("~/.ssh/id_rsa")
        if not path.exists(fname):
            print("Creating ssh key pair")
            # returns non-0 if the key pair already exists
            call(["ssh-keygen", "-f", fname, "-t", "rsa", "-b", "4096", "-m", "PEM", "-N", ""])

    def is_host_known(self, hostname=None):
        """Check if the host is known already."""
        if hostname is None:
            hostname = self.hostname
        fname = path.expanduser("~/.ssh/known_hosts")
        if not path.exists(fname):
            return False
        return call(["ssh-keygen", "-F", hostname]) == 0

    def _make_host_known(self, hostname, proxycmd=None):
        """Add host information into known_hosts file."""
        proxycmd = [] if proxycmd is None else proxycmd
        fname = path.expanduser("~/.ssh/known_hosts")
        print(f"Adding keys from {hostname} to {fname}")
        hashes = check_output(proxycmd + ["ssh-keyscan", "-p", str(self.port), "-H", hostname])
        with open(fname, "a") as fobj:
            fobj.write(hashes.decode("utf-8"))

    def can_login(self, silent=False):
        """Check if it is possible to login into the remote host."""
        if self.username is None:  # if I can't find the username - I must fail
            return False
        userhost = self.username + "@" + self.hostname
        if not silent:
            print(f"Trying ssh {userhost} -p {self.port}... ", end='')
        # With BatchMode on, no password prompt or other interaction is attempted,
        # so a connect that requires a password will fail.
        ret = call(["ssh", userhost, "-p", str(self.port), "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "true"])
        if not silent:
            print("Ok" if ret == 0 else "Failed")
        return ret == 0

    def is_in_config(self):
        """Check if the config file contains host information."""
        fname = path.expanduser("~/.ssh/config")
        if not path.exists(fname):
            return False
        cfglines = open(fname).read().split("\n")
        return "Host " + self.hostname in cfglines

    def _write_ssh_config(self, proxycmd='', private_key_abs_fname=None):
        """Put host information into the config file."""
        fname = path.expanduser("~/.ssh/config")
        print(f"Adding section to {fname}")
        with open(fname, "a") as file:
            file.write(f"Host {self.hostname} \n")
            file.write(f"User {self.username} \n")
            file.write(f"Port {self.port} \n")
            if private_key_abs_fname:
                file.write(f"IdentityFile {private_key_abs_fname} \n")
            if proxycmd:
                file.write(f"ProxyCommand ssh -q -Y {proxycmd} netcat %h %p\n")
            file.write("ServerAliveInterval 5\n")

    @staticmethod
    def _add_private_key(private_key_fname, private_key_content):
        """
        param private_key_fname: string
        param private_key_content: bytes
        """
        fname = path.expanduser(f"~/.ssh/{private_key_fname}")
        if path.exists(fname):
            # if file already exist and have the same content
            with open(fname, "rb") as file:
                content = file.read()
                if content == private_key_content:
                    return path.basename(fname)

            fname = fname + '_' + shortuuid.uuid()
        with open(fname, "wb") as file:
            file.write(private_key_content)

        os.chmod(fname, 0o600)

        return fname

    @staticmethod
    def _send_pubkey(hostname, username, password, proxycmd=''):
        """Send a publick key to a remote host."""
        from pexpect import TIMEOUT
        timeout = 10
        print("Sending public key to {}... ".format(hostname), end='')
        str_ssh = 'ssh-copy-id {}@{}'.format(username, hostname)
        if proxycmd:
            str_ssh += ' -o "ProxyCommand ssh -q -Y ' + proxycmd + ' netcat %h %p\n"'
        child = pexpect.spawn(str_ssh)
        try:
            index = child.expect(
                [
                    "s password:",  # 0
                    "All keys were skipped because they already exist on the remote system",  # 1
                    "ERROR: No identities found",  # 2
                    "Could not resolve hostname",  # 3
                    pexpect.EOF
                ],
                timeout=timeout)  # final
        except TIMEOUT:
            print("Exceeded {} s timeout".format(timeout))
            return False

        possible_output = {
            1: {
                'message': "Keys are already present on the remote machine",
                'status': True
            },
            2: {
                'message': "Failed\nLooks like the key pair is not present in ~/.ssh folder",
                'status': False
            },
            3: {
                'message': "Failed\nUnknown hostname",
                'status': False
            },
        }
        if index == 0:
            child.sendline(password)
            try:
                child.expect("Now try logging into", timeout=5)
            except TIMEOUT:
                print("Failed\nPlease check your username and/or password")
                return False
            print("Ok")
            child.close()
            return True

        if index in possible_output:
            print(possible_output[index]['message'])
            return possible_output[index]['status']

        print("Failed\nUnknown problem")
        print(child.before, child.after)
        child.close()
        return False

    def _configure_proxy(self, password, proxy_password):
        """Configure proxy server."""

        # If proxy IS required.
        if self.use_proxy:
            # Again, some standard checks whether proxy server parameters are provided.
            if self.proxy_hostname is None:  # hostname
                print("Please specify the proxy server hostname")
                return False, ''

            # If proxy username and password should be different from the main computer - they must be provided.
            if self._use_diff_proxy_username.value:

                # Check username.
                if self.proxy_username is not None:
                    proxy_username = self.proxy_username
                else:
                    print("Please specify the proxy server username")
                    return False, ''

                # Check password.
                if not proxy_password.strip():
                    print("Please specify the proxy server password")
                    return False, ''

            # If username and password are the same as for the main computer.
            else:
                proxy_username = self.username
                proxy_password = password

            # Make proxy server known.
            if not self.is_host_known(self.proxy_hostname):
                self._make_host_known(self.proxy_hostname)

            # Finally trying to connect.
            if self._send_pubkey(self.proxy_hostname, proxy_username, proxy_password):
                return True, proxy_username + '@' + self.proxy_hostname

            print(f"Could not send public key to {self.proxy_hostname} (proxy server).")
            return False, ''

        # If proxy is NOT required.
        return True, ''

    def on_setup_ssh(self, change):
        """Setup ssh, password and private key are supported"""
        with self._setup_ssh_out:
            mode = self._verification_mode.value
            self._on_setup_ssh(mode, change)

    def _on_setup_ssh(self, mode, change):  # pylint: disable=unused-argument,too-many-return-statements,too-many-branches
        """ATTENTION: modifying the order of operations in this function can lead to unexpected problems"""
        clear_output()

        # If hostname is not provided - do not do anything.
        if self.hostname is None:  # check hostname
            print("Please specify the computer hostname")
            return

        # Check if password-free access was enabled earlier.
        if self.can_login():
            print("Password-free access is already enabled")
            # It can still happen that password-free access is enabled
            # but host is not present in the config file - fixing this.
            if not self.is_in_config():
                self._write_ssh_config()  # We do not use proxy here, because if computer
                # can be accessed without any info in the config - proxy is not needed.
                self.setup_counter += 1  # Only if config file has changed - increase setup_counter.
            return

        # If couldn't login in the previous step, chek whether all required information is provided.
        if self.username is None:  # check username
            print("Please enter your ssh username")
            return

        if mode == 'password':
            self._ssh_keygen()
            # Temporary passwords.
            password = self.__password
            proxy_password = self.__proxy_password
            private_key_abs_fname = None
            if not password.strip():  # check password
                print("Please enter your ssh password")
                return
        if mode == 'private_key':
            # unwrap private key file and setting temporary private_key content
            private_key_fname, private_key_content = self.__private_key
            proxy_password = self.__proxy_password
            password = None
            if private_key_fname is None:  # check private key file
                print("Please upload your private key file")
                return

            # write private key in ~/.ssh/ and use the name of upload file,
            # if exist, generate random string and append to filename then override current name.
            private_key_abs_fname = self._add_private_key(private_key_fname, private_key_content)

        # get the right commands to access the proxy server (if provided)
        success, proxycmd = self._configure_proxy(password, proxy_password)
        if not success:
            return

        # make host known by ssh on the proxy server
        if not self.is_host_known():
            self._make_host_known(self.hostname, ['ssh'] + [proxycmd] if proxycmd else [])

        if mode == 'password':
            # sending public key to the main host
            if not self._send_pubkey(self.hostname, self.username, password, proxycmd):
                print("Could not send public key to {self.hostname}")
                return

        # modify the ssh config file if necessary
        if not self.is_in_config():
            self._write_ssh_config(proxycmd, private_key_abs_fname)

        # FOR LATER: add a check if new config is different from the current one. If so
        # infrom the user about it.

        # final check
        if self.can_login():
            self.setup_counter += 1
            print("Automatic ssh setup successful :-)")
            return
        print("Automatic ssh setup failed, sorry :-(")
        return

    def on_use_verification_mode_change(self, change):  # pylint: disable=unused-argument
        """which verification mode is chosen."""
        if self._verification_mode.value == 'password':
            self._inp_password.disabled = False
            self._inp_private_key.disabled = True
        if self._verification_mode.value == 'private_key':
            self._inp_password.disabled = True
            self._inp_private_key.disabled = False

    def on_use_proxy_change(self, change):
        """If proxy check-box is clicked."""
        if change['new']:
            self._proxy_ssh_box.layout.visibility = 'visible'
        else:
            self._proxy_ssh_box.layout.visibility = 'hidden'
            self._use_diff_proxy_username.value = False

    def on_use_diff_proxy_username_change(self, change):  # pylint: disable=unused-argument
        """If using different username for proxy check-box is clicked."""
        if change['new']:
            self._proxy_user_password_box.layout.visibility = 'visible'
        else:
            self._proxy_user_password_box.layout.visibility = 'hidden'


# Keep this function only because it might be used later.
# What it does: looks inside .ssh/config file and loads computer setup from
# there (if present)
#     def _get_from_config(self, b):
#         config = parse_sshconfig(self.hostname)
#         if 'user' in config:
#             self._inp_username.value = config['user']
#         else:
#             self._inp_username.value = ''
#         if 'proxycommand' in config:
#             self._use_proxy.value = True
#             proxy = ''.join([ s for s in config['proxycommand'].split() if '@' in s])
#             username, hostname = proxy.split('@')
#             self._inp_proxy_address.value = hostname
#             if username != self.username:
#                 self._use_diff_proxy_username.value = True
#                 self.proxy_username = username
#         else:
#             self._use_proxy.value = False

    @property
    def __password(self):
        """Returning the password and immediately destroying it"""
        passwd = copy(self._inp_password.value)
        self._inp_password.value = ''
        return passwd

    @property
    def __proxy_password(self):
        """Returning the password and immediately destroying it"""
        passwd = copy(self._inp_proxy_password.value)
        self._inp_proxy_password.value = ''
        return passwd

    @property
    def __private_key(self):
        """unwrap private key file and setting filename and file content"""
        if self._inp_private_key.value:
            (fname, _value), *_ = self._inp_private_key.value.items()
            content = copy(_value['content'])
            self._inp_private_key.value.clear()
            self._inp_private_key._counter = 0  # pylint: disable=protected-access
            return fname, content
        return None, None

    @validate('proxy_hostname')
    def _validate_proxy_hostname(self, provided):
        """Enable 'use proxy' widget if proxy hostname is provided."""
        if provided['value']:
            self.use_proxy = True
        return provided['value']

    @validate('proxy_username')
    def _validate_proxy_username(self, provided):
        """Enable 'use proxy' and 'use different proxy username' widgets if proxy username is provided."""
        if provided['value']:
            self.use_proxy = True
            self._use_diff_proxy_username.value = True
        return provided['value']

    @validate('port')
    def _validate_port(self, provided):  # pylint: disable=no-self-use
        return int(provided['value'])


class AiidaComputerSetup(ipw.VBox):
    """Inform AiiDA about a computer."""
    label = Unicode()
    hostname = Unicode()
    description = Unicode()
    work_dir = Unicode()
    mpirun_command = Unicode()
    mpiprocs_per_machine = Union([Unicode(), Int()])
    prepend_text = Unicode()
    append_text = Unicode()
    transport = Unicode()
    scheduler = Unicode()

    def __init__(self, **kwargs):
        from aiida.transports import Transport
        from aiida.schedulers import Scheduler

        # List of widgets to be displayed.
        inp_computer_name = ipw.Text(value='',
                                     placeholder='Will only be used within AiiDA',
                                     description="AiiDA computer name:",
                                     layout=ipw.Layout(width="500px"),
                                     style=STYLE)
        link((inp_computer_name, 'value'), (self, 'label'))

        # Hostname.
        inp_computer_hostname = ipw.Text(description="Hostname:", layout=ipw.Layout(width="500px"), style=STYLE)
        link((inp_computer_hostname, 'value'), (self, 'hostname'))

        # Computer description.
        inp_computer_description = ipw.Text(value='',
                                            placeholder='No description (yet)',
                                            description="Computer description:",
                                            layout=ipw.Layout(width="500px"),
                                            style=STYLE)
        link((inp_computer_description, 'value'), (self, 'description'))

        # Directory where to run the simulations.
        inp_computer_workdir = ipw.Text(value='/scratch/{username}/aiida_run',
                                        description="Workdir:",
                                        layout=ipw.Layout(width="500px"),
                                        style=STYLE)
        link((inp_computer_workdir, 'value'), (self, 'work_dir'))

        # Mpirun command.
        inp_mpirun_cmd = ipw.Text(value='mpirun -n {tot_num_mpiprocs}',
                                  description="Mpirun command:",
                                  layout=ipw.Layout(width="500px"),
                                  style=STYLE)
        link((inp_mpirun_cmd, 'value'), (self, 'mpirun_command'))

        # Number of CPUs per node.
        inp_computer_ncpus = ipw.IntText(value=12,
                                         step=1,
                                         description='Number of CPU(s) per node:',
                                         layout=ipw.Layout(width="270px"),
                                         style=STYLE)
        link((inp_computer_ncpus, 'value'), (self, 'mpiprocs_per_machine'))

        inp_transport_type = ipw.Dropdown(value='ssh',
                                          options=Transport.get_valid_transports(),
                                          description="Transport type:",
                                          style=STYLE)
        link((inp_transport_type, 'value'), (self, 'transport'))

        # Scheduler.
        inp_scheduler = ipw.Dropdown(value='slurm',
                                     options=Scheduler.get_valid_schedulers(),
                                     description="Scheduler:",
                                     style=STYLE)
        link((inp_scheduler, 'value'), (self, 'scheduler'))

        # Use login shell.
        self._use_login_shell = ipw.Checkbox(value=True, description="Use login shell")

        # Prepend text.
        inp_prepend_text = ipw.Textarea(placeholder='Text to prepend to each command execution',
                                        description='Prepend text:',
                                        layout=ipw.Layout(width="400px"))
        link((inp_prepend_text, 'value'), (self, 'prepend_text'))

        # Append text.
        inp_append_text = ipw.Textarea(placeholder='Text to append to each command execution',
                                       description='Append text:',
                                       layout=ipw.Layout(width="400px"))
        link((inp_append_text, 'value'), (self, 'append_text'))

        # Buttons and outputs.
        btn_setup_comp = ipw.Button(description="Setup computer")
        btn_setup_comp.on_click(self._on_setup_computer)
        btn_test = ipw.Button(description="Test computer")
        btn_test.on_click(self.test)
        self._setup_comp_out = ipw.Output(layout=ipw.Layout(width="500px"))
        self._test_out = ipw.Output(layout=ipw.Layout(width="500px"))

        # Organize the widgets
        children = [
            ipw.HBox([
                ipw.VBox([
                    inp_computer_name,
                    inp_computer_hostname,
                    inp_computer_description,
                    inp_computer_workdir,
                    inp_mpirun_cmd,
                    inp_computer_ncpus,
                    inp_transport_type,
                    inp_scheduler,
                    self._use_login_shell,
                ]),
                ipw.VBox([inp_prepend_text, inp_append_text])
            ]),
            ipw.HBox([btn_setup_comp, btn_test]),
            ipw.HBox([self._setup_comp_out, self._test_out]),
        ]
        super(AiidaComputerSetup, self).__init__(children, **kwargs)

    def _configure_computer(self):
        """Create AuthInfo."""
        print("Configuring '{}'".format(self.label))
        sshcfg = parse_sshconfig(self.hostname)
        authparams = {
            'compress': True,
            'key_filename': os.path.expanduser(sshcfg.get('identityfile', ['~/.ssh/id_rsa'])[0]),
            'gss_auth': False,
            'gss_deleg_creds': False,
            'gss_host': self.hostname,
            'gss_kex': False,
            'key_policy': 'WarningPolicy',
            'load_system_host_keys': True,
            'port': sshcfg.get('port', 22),
            'timeout': 60,
            'use_login_shell': self._use_login_shell.value,
        }
        if 'user' in sshcfg:
            authparams['username'] = sshcfg['user']
        else:
            print(f"SSH username is not provided, please run `verdi computer configure {self.label}` "
                  "from the command line.")
            return
        if 'proxycommand' in sshcfg:
            authparams['proxy_command'] = sshcfg['proxycommand']
        aiidauser = User.objects.get_default()
        from aiida.orm import AuthInfo
        authinfo = AuthInfo(computer=Computer.objects.get(name=self.label), user=aiidauser)
        authinfo.set_auth_params(authparams)
        authinfo.store()
        print(check_output(['verdi', 'computer', 'show', self.label]).decode('utf-8'))

    def _on_setup_computer(self, _=None):
        """When setup computer button is pressed."""
        with self._setup_comp_out:
            clear_output()
            if self.label is None:  # check hostname
                print("Please specify the computer name (for AiiDA)")
                return
            try:
                computer = Computer.objects.get(name=self.label)
                print(f"A computer called {self.label} already exists.")
                return
            except NotExistent:
                pass

            print(f"Creating new computer with name '{self.label}'")
            computer = Computer(name=self.label, hostname=self.hostname, description=self.description)
            computer.set_transport_type(self.transport)
            computer.set_scheduler_type(self.scheduler)
            computer.set_workdir(self.work_dir)
            computer.set_mpirun_command(self.mpirun_command.split())
            computer.set_default_mpiprocs_per_machine(self.mpiprocs_per_machine)
            if self.prepend_text:
                computer.set_prepend_text(self.prepend_text)
            if self.append_text:
                computer.set_append_text(self.append_text)

            computer.store()
            self._configure_computer()

    def test(self, _=None):
        with self._test_out:
            clear_output()
            print(check_output(['verdi', 'computer', 'test', '--print-traceback', self.label]).decode('utf-8'))

    @validate('mpiprocs_per_machine')
    def _validate_mpiprocs_per_machine(self, provided):  # pylint: disable=no-self-use
        return int(provided['value'])


class ComputerDropdown(ipw.VBox):
    """Widget to select a configured computer.

    Attributes:
        selected_computer(Unicode or Computer): Trait that points to the selected Computer instance.
            It can be set either to an AiiDA Computer instance or to a computer label (will
            automatically be replaced by the corresponding Computer instance). It is linked to the
            'value' trait of `self._dropdown` widget.

        computers(Dict): Trait that contains a dictionary (label => Computer instance) for all
        computers found in the AiiDA database. It is linked to the 'options' trait of
        `self._dropdown` widget.

        allow_select_disabled(Bool):  Trait that defines whether to show disabled computers.
    """

    selected_computer = Union([Unicode(), Instance(Computer)], allow_none=True)
    computers = Dict(allow_none=True)
    allow_select_disabled = Bool(False)

    def __init__(self, description='Select computer:', path_to_root='../', **kwargs):
        """Dropdown for configured AiiDA Computers.

        description (str): Text to display before dropdown.

        path_to_root (str): Path to the app's root folder.
        """

        self.output = ipw.Output()

        self._dropdown = ipw.Dropdown(options={},
                                      value=None,
                                      description=description,
                                      style={'description_width': 'initial'},
                                      disabled=True)
        link((self, 'computers'), (self._dropdown, 'options'))
        link((self._dropdown, 'value'), (self, 'selected_computer'))

        btn_refresh = ipw.Button(description="Refresh", layout=ipw.Layout(width="70px"))
        btn_refresh.on_click(self.refresh)

        self.observe(self.refresh, names='allow_select_disabled')

        self._setup_another = ipw.HTML(
            value=f"""<a href={path_to_root}aiidalab-widgets-base/setup_computer.ipynb target="_blank">
            Setup new computer</a>""")

        children = [ipw.HBox([self._dropdown, btn_refresh, self._setup_another]), self.output]
        self.refresh()
        super().__init__(children=children, **kwargs)

    def _get_computers(self):
        """Get the list of available computers."""

        # Getting the current user.
        user = User.objects.get_default()

        return {
            c[0].name: c[0]
            for c in QueryBuilder().append(Computer).all()
            if c[0].is_user_configured(user) and (self.allow_select_disabled or c[0].is_user_enabled(user))
        }

    def refresh(self, _=None):
        """Refresh the list of configured computers."""

        with self.output:
            clear_output()
            with self.hold_trait_notifications():  # pylint: disable=not-context-manager
                self._dropdown.options = self._get_computers()
            if not self.computers:
                print("No computers found.")
                self._dropdown.disabled = True
            else:
                self._dropdown.disabled = False

            self._dropdown.value = None

    @validate('selected_computer')
    def _validate_selected_computer(self, change):
        """Select computer either by name or by class instance."""
        computer = change['value']

        if not computer:
            return None
        if isinstance(computer, str):
            if computer in self.computers:
                return self.computers[computer]
            raise KeyError(f"No computer named '{computer}' was found in AiiDA database.")

        if isinstance(computer, Computer):
            if computer.name in self.computers:
                return computer
            raise ValueError(f"The computer instance '{computer}' supplied was not found in  the AiiDA database. "
                             "Consider reloading")

        # This place will never be reached, because the trait's type is checked before validation.
        return None
