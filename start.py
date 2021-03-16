"""Start page appearance."""
import ipywidgets as ipw

TEMPLATE = """
<table>
<tr>
  <th style="text-align:center">Basic data objects.</th>
  <th style="width:70px" rowspan=2></th>
  <th style="text-align:center">Codes and computers.</th>
  <th style="width:70px" rowspan=2></th>
  <th style="text-align:center">Processes.</th>
  <th style="width:70px" rowspan=2></th>
  <th style="text-align:center">Electronic Lab Notebook.</th>
<tr>
  <td valign="top"><ul>
    <li><a href="{appbase}/structures.ipynb" target="_blank">Dealing with one structure</a></li>
    <li><a href="{appbase}/aiida_datatypes_viewers.ipynb" target="_blank">AiiDA datatypes viewers</a></li>
  </ul></td>
  <td valign="top"><ul>
    <li><a href="{appbase}/setup_computer.ipynb" target="_blank">Setup computer</a></li>
    <li><a href="{appbase}/setup_code.ipynb" target="_blank">Setup code</a></li>
    <li><a href="{appbase}/codes_computers.ipynb" target="_blank">Dealing with codes and computers</a></li>
  </ul></td>
  <td valign="top"><ul>
    <li><a href="{appbase}/process_list.ipynb" target="_blank">Process list</a></li>
    <li><a href="{appbase}/process.ipynb" target="_blank">Follow a process</a></li>
  </ul></td>
  <td valign="top"><ul>
    <li><a href="{appbase}/eln_import.ipynb" target="_blank">Import from ELN</a></li>
    <li><a href="{appbase}/eln_export.ipynb" target="_blank">Export to ELN</a></li>
  </ul></td>
</tr>
</table>
"""


def get_start_widget(appbase, jupbase, notebase):
    html = TEMPLATE.format(appbase=appbase, jupbase=jupbase, notebase=notebase)
    return ipw.HTML(html)


# EOF
