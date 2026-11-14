# MICrONS Mouse Connectome Explorer

A free, local Streamlit app for exploring neuronal connectivity in the MICrONS mouse visual-cortex dataset. Enter a neuron ID to inspect its incoming and outgoing synaptic partners, review cell annotations, compare two neurons, inspect available visual-response summaries, and open a 3D Neuroglancer view.

The app runs on your computer and queries the public MICrONS/CAVE services directly. It does not use an AI API or a paid hosted service.

## Features

- **Connectivity explorer:** query input and output synapses for a neuron and rank its partners by synapse count.
- **Cell annotations:** optionally enrich partners with cell type, classification, and proofreading information; filter the results by annotation, proofreading status, or text.
- **Two-neuron comparison:** compare shared input or output partners and see overlap statistics.
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

1. Enter a MICrONS `pt_root_id` (root IDs can change as neuron reconstructions are revised).
2. Choose the connectivity directions and, if useful, enable annotation enrichment and filters.
3. Optionally enter a second root ID to compare partners.
4. Review the connectivity table, available visual-response summary, and CSV download.
5. Generate a Neuroglancer view when you want to inspect the selected neurons in 3D.

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
