import io
import ipywidgets as ipw
from aiida.orm import load_node
import traitlets
from aiida.plugins import DataFactory
import urllib.parse as urlparse
from cheminfopy import Sample
from aiida.orm import Node, QueryBuilder
from IPython.display import clear_output, display, Javascript

import tempfile
import json
from pathlib import Path

from .viewers import viewer

TOKEN_FILE_PATH = Path(tempfile.gettempdir()) / "aiidalab-eln-tokens.json"


def get_token(token_type, uuid):
    token_file = TOKEN_FILE_PATH
    try:
        with open(token_file, "r") as file:
            tokens = json.load(file)
            return tokens[token_type][uuid]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def update_token(token_type, uuid, token):
    token_file = TOKEN_FILE_PATH
    try:
        with open(token_file, "r") as file:
            tokens = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        tokens = {}

    if token_type not in tokens:
        tokens[token_type] = {}
    tokens[token_type][uuid] = token

    with open(token_file, "w") as file:
        json.dump(tokens, file, indent=4)


class ElnImportWidget(ipw.VBox):

    node = traitlets.Instance(Node, allow_none=True)

    def __init__(self, url, **kwargs):
        self._output = ipw.Output()
        self.node = self.eln_import(url)

        self.btn_store = ipw.Button(description="Store in AiiDA")
        self.btn_store.on_click(self.store_node)

        self.btn_send_to_app = ipw.Button(description="Open in an App.", disabled=True)
        self.btn_send_to_app.on_click(self.send_to_app)

        self.select_app = ipw.Dropdown(
            options=[
                ("lsmo/optimization", "../aiidalab-lsmo/multistage_geo_opt_ddec.ipynb"),
                ("QE", "../quantum-espresso/qe.ipynb"),
            ],
            disabled=True,
        )

        self.user_output = ipw.HTML("")

        children = [
            self._output,
            ipw.HBox([self.btn_store, self.user_output]),
            ipw.HBox([self.btn_send_to_app, self.select_app]),
        ]
        super().__init__(children=children, **kwargs)

    def eln_import(self, url, object_type="cif"):
        object_type = DataFactory(object_type)
        url = urlparse.urlsplit(url)

        try:
            parsed_url = urlparse.parse_qs(url.query)
            self.eln_instance = parsed_url["instance"][0]
            self.sample_uuid = parsed_url["sample_uuid"][0]
            self.spectrum_type = parsed_url["spectrum_type"][0]
            self.file_name = parsed_url["name"][0]
        except KeyError:
            return None

        if "sample_token" in parsed_url:
            sample_token = parsed_url["sample_token"][0]
            update_token("sample", self.sample_uuid, sample_token)
        else:
            sample_token = get_token("sample", self.sample_uuid)

        sample = Sample(
            instance=self.eln_instance, sample_uuid=self.sample_uuid, token=sample_token
        )
        content = sample.get_spectrum(
            spectrum_type=self.spectrum_type, name=self.file_name
        )
        file = io.BytesIO(bytes(content, "utf8"))
        return object_type(file=file)

    @traitlets.observe("node")
    def _observe_node(self, change):
        if change["new"] != change["old"]:
            with self._output:
                clear_output()
                if change["new"]:
                    display(viewer(change["new"]))

    def store_node(self, _=None):
        eln_info = {
            "eln_instance": self.eln_instance,
            "sample_uuid": self.sample_uuid,
            "spectrum_type": self.spectrum_type,
            "file_name": self.file_name,
        }
        self.node.set_extra("eln", eln_info)
        self.node.store()
        self.user_output.value = "Stored in AiiDA [{}]".format(self.node)
        self.btn_send_to_app.disabled = False
        self.select_app.disabled = False

    def send_to_app(self, _=None):
        app = self.select_app.value
        url = f"https://aiidalab-demo.materialscloud.org/user-redirect/apps/apps/aiidalab-widgets-base/{app}?structure_uuid={self.node.uuid}"
        display(Javascript(f'window.open("{url}");'))


class ElnExportWidget(ipw.VBox):
    def __init__(self, uuid, **kwargs):
        self.node = load_node(uuid)
        self.eln_instance = ipw.Text(
            description="ELN:",
            value="",
            style={"description_width": "initial"},
        )
        self.sample_uuid = ipw.Text(
            description="Sample ID:",
            value="",
            style={"description_width": "initial"},
        )
        self.spectrum_type = ipw.Text(
            description="Spectrum Type:",
            value="",
            style={"description_width": "initial"},
        )
        self.file_name = ipw.Text(
            description="File name:",
            value=self.node.uuid,
            style={"description_width": "initial"},
        )
        self.token = ipw.Text(
            description="Token:",
            value="",
            style={"description_width": "initial"},
        )

        title = ipw.HTML("<h3>Export to ELN:</h3>")

        self.send = ipw.Button(description="Send to ELN")
        self.send.on_click(self.send_to_eln)

        vwr = viewer(self.node)

        self.parse_node()

        children = [
            vwr,
            title,
            self.eln_instance,
            self.sample_uuid,
            self.file_name,
            self.token,
            self.send,
        ]
        super().__init__(children=children, **kwargs)

    def parse_node(self):
        node = self.node
        info = {}
        if "eln" in self.node.extras:
            info = self.node.extras["eln"]
        else:
            try:
                q = QueryBuilder().append(
                    Node,
                    filters={"extras": {"has_key": "eln"}},
                    tag="source_node",
                    project="extras.eln",
                )
                q.append(
                    Node, filters={"uuid": node.uuid}, with_ancestors="source_node"
                )
                info = q.all(flat=True)[0]
            except IndexError:
                pass
        if info:
            self.eln_instance.value = info["eln_instance"]
            self.sample_uuid.value = info["sample_uuid"]
            self.spectrum_type.value = info["spectrum_type"]
            self.token.value = get_token("sample", info["sample_uuid"])

    def send_to_eln(self, _=None):
        sample = Sample(
            self.eln_instance.value,
            sample_uuid=self.sample_uuid.value,
            token=self.token.value,
        )

        source_info = {
            "uuid": self.node.uuid,
            "url": "https://aiidalab-demo.materialscloud.org/hub/login",
            "name": "Isotherm simulated using the isotherm app on AiiDAlab",
        }
        sample.put_spectrum(
            spectrum_type=self.spectrum_type.value,
            name=self.file_name.value,
            filecontent=self.node.get_content(),
            source_info=source_info,
        )
