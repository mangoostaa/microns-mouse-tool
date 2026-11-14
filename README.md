# MICrONS Mouse Connectome Explorer

A free, local Streamlit app for exploring neuronal connectivity in the MICrONS mouse visual-cortex dataset. Enter a neuron ID to inspect its incoming and outgoing synaptic partners, review cell annotations, compare two neurons, inspect available visual-response summaries, and open a 3D Neuroglancer view.

The app runs on your computer and queries the public MICrONS/CAVE services directly. It does not use an AI API or a paid hosted service.

## Features

- **Connectivity explorer:** query input and output synapses for a neuron and rank its partners by synapse count.
- **Cell annotations:** optionally enrich partners with cell type, classification, and proofreading information; filter the results by annotation, proofreading status, or text.
- **Two-neuron comparison:** compare shared input or output partners and see overlap statistics.
- **Saved, repeatable queries:** export a JSON query file with neuron IDs, filters, datastack, and CAVE materialization. Load it later to restore the settings and rerun the analysis against that saved materialization when it is available.
- **Complete analysis bundles:** download a ZIP containing the query manifest, provenance notes, and the result tables for connectivity, visual-response properties, comparisons, or group analysis.
- **Group analysis:** submit up to 50 neuron root IDs to get per-neuron input/output summaries and a ranked list of partners shared across the group, with the fraction of queried neurons connected to each partner. A progress bar shows which neuron is being queried. Export both tables as CSV or as a complete ZIP bundle.
- **Visual-response summaries:** view available Digital Twin properties such as preferred orientation/direction and selectivity, with manual or automated correspondence options. A plot summarizes available cells; it is not a raw response trace or a full tuning curve.
- **3D view:** create a Neuroglancer link showing the queried neuron and its synaptic partners.
- **CSV export:** download the filtered connectivity results for further analysis.

## Requirements

- Windows 10/11 (the included launcher is a Windows batch file).
- Python 3.10 or later.
- Internet access to MICrONS/CAVE and Neuroglancer services.
- A CAVE token associated with an account that has accepted the MICrONS dataset Terms of Service.

## Setup

1. Install Python from [python.org](https://www.python.org/downloads/windows/). Enable **Add Python to PATH** in the installer.
2. Sign in to the [MICrONS/CAVE portal](https://global.daf-apis.com/) with your Google account and accept the dataset Terms of Service.
3. In PowerShell, open this project directory and run the launcher:

   ```powershell
   .\INICIAR.bat
   ```

   On first launch, it creates a local virtual environment and installs the packages in `requirements.txt`. Streamlit then opens the app at `http://localhost:8501`.

4. If CAVE asks for authentication, create a token at [the CAVE token page](https://global.daf-apis.com/auth/api/v1/create_token), then save it locally. After the launcher has created `.venv`, run:

   ```powershell
   .\.venv\Scripts\python.exe -c "from caveclient import CAVEclient; c=CAVEclient(); token=input('Paste your CAVE token: ').strip(); c.auth.save_token(token=token, overwrite=True)"
   ```

   The command stores the token in CAVE's user configuration, outside this repository. `overwrite=True` replaces an existing locally saved token. Never paste a token into source files, GitHub, screenshots, or issue reports. Creating a replacement token may invalidate the previous one.

To start the app manually after setup:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Using the app

1. Enter a MICrONS `pt_root_id` (root IDs can change as neuron reconstructions are revised) and run the query.
2. Optionally add a second ID to compare partner overlap. Enable annotations and filters as needed.
3. Download a JSON file to save the query settings and data provenance. Load this file from the sidebar later, apply its settings, and run the query again.
4. For population analysis, paste up to 50 IDs into **Group analysis** (one per line, comma, or semicolon). The tool reports counts for each neuron and summarizes partners by how many group members connect to them.
5. Download individual CSV tables or a ZIP bundle containing the tables and query manifest. Review visual-response summaries or generate a Neuroglancer view for 3D inspection.

Group analysis makes two CAVE synapse queries per neuron (input and output), so larger lists can take longer. Queries are run from your computer using your CAVE credentials.

Synapse counts describe the number of reconstructed synapses in the queried materialization; they are not a direct measurement of functional connection strength. Record the CAVE materialization/version shown by the app when you need reproducible analysis. Not every neuron has a corresponding functional record.

### 3D link and data sharing

The Neuroglancer state service stores the view state needed to open a generated link. That state can include neuron IDs and synapse locations, and anyone with the link may be able to view it. Do not create or share a link for data you need to keep private.

## Data and references

- [MICrONS Explorer: cortical mm³](https://www.microns-explorer.org/cortical-mm3)
- [CAVE client setup](https://tutorial.microns-explorer.org/quickstart_notebooks/01-caveclient-setup.html)
- [Querying synapses](https://tutorial.microns-explorer.org/quickstart_notebooks/04-cave-query-synapses.html)
- [MICrONS annotation tables and functional properties](https://tutorial.microns-explorer.org/annotation-tables.html)
- [Neuroglancer and NGLui tutorial](https://tutorial.microns-explorer.org/quickstart_notebooks/09-nglui-neuroglancer.html)
- MICrONS Consortium, *Nature* (2025), [DOI: 10.1038/s41586-025-08790-w](https://doi.org/10.1038/s41586-025-08790-w)

## License

No license is currently included in this repository. Ask the repository owner before redistributing or reusing the code.
