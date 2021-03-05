import io
import ipywidgets as ipw
from aiida.orm import load_node
from aiida.plugins import DataFactory
import urllib.parse as urlparse
from c6h6py import Sample

from .viewers import viewer


def eln_import(url, object_type="cif"):
    object_type = DataFactory(object_type)
    url = urlparse.urlsplit(url)
    try:
        parsed_url = urlparse.parse_qs(url.query)
        eln_instance = parsed_url["elnInstance"][0]
        sample_uuid = parsed_url["sampleId"][0]
        token = parsed_url["sampleToken"][0]
        file_path = parsed_url["filePath"][0]
    except KeyError:
        return None
    sample = Sample(eln_instance, sample_uuid=sample_uuid, token=token)
    content = sample.get_attachment(file_path)
    file = io.BytesIO(bytes(content, "utf8"))
    return object_type(file=file)


class ElnExportWidget(ipw.VBox):
    def __init__(self, uuid, **kwargs):
        self.object = load_node(uuid)
        self.eln = ipw.Text(
            description="ELN:",
            value="https://mydb.cheminfo.org/db/eln/",
            style={"description_width": "initial"},
        )
        self.sample_uuid = ipw.Text(
            description="Sample ID:",
            value="3f3aa0cf7244e0ce5f359f1a3023e377",
            style={"description_width": "initial"},
        )
        self.file_name = ipw.Text(
            description="File name:",
            value=self.object.uuid,
            style={"description_width": "initial"},
        )
        self.token = ipw.Text(
            description="Token:",
            value="",
            style={"description_width": "initial"},
        )

        title = ipw.HTML("<h3>Export to ELN:</h3>")

        self.send = ipw.Button(description="Send to ELN")

        def send_to_eln(_=None):
            sample = Sample(
                self.eln.value,
                sample_uuid=self.sample_uuid.value,
                token=self.token.value,
            )
            sample.put_attachment(
                "xray", f"{self.file_name.value}", self.object.get_content()
            )

        self.send.on_click(send_to_eln)

        vwr = viewer(self.object)

        children = [
            vwr,
            title,
            self.eln,
            self.sample_uuid,
            self.file_name,
            self.token,
            self.send,
        ]
        super().__init__(children=children, **kwargs)
