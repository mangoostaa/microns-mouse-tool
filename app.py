import json
from io import BytesIO
from datetime import datetime, timezone
from zipfile import ZIP_DEFLATED, ZipFile

import streamlit as st
import pandas as pd
from caveclient import CAVEclient


DATASTACK = "minnie65_public"
EXAMPLE_ID = 864691136968109774


def build_export_bundle(manifest, tables):
    """Package result tables with the query settings and data provenance."""
    bundle = BytesIO()
    with ZipFile(bundle, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("query.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr(
            "README.txt",
            "MICrONS Connectome Explorer analysis export\n\n"
            "query.json records the selected IDs, filters, datastack, and materialization.\n"
            "CSV tables contain the results shown by the app for this analysis.\n"
            "Synapse counts describe reconstructed anatomical synapses; they are not a direct\n"
            "measurement of functional connection strength. Root IDs and results may change\n"
            "between materializations as neuron reconstructions are revised.\n",
        )
        for filename, frame in tables.items():
            if frame is not None and not frame.empty:
                archive.writestr(filename, frame.to_csv(index=False).encode("utf-8-sig"))
    return bundle.getvalue()


def summarize_direction(synapses, partner_column, result_column):
    if synapses.empty:
        return pd.DataFrame(
            {"Partner ID": pd.Series(dtype="uint64"), result_column: pd.Series(dtype="int64")}
        )
    return (
        synapses.groupby(partner_column, as_index=False)
        .size()
        .rename(columns={partner_column: "Partner ID", "size": result_column})
    )


def merge_root_annotations(partners, annotations):
    left = partners.copy()
    right = annotations.copy()
    left["_join_root_id"] = left["Partner ID"].astype("string")
    right["_join_root_id"] = right["pt_root_id"].astype("string")
    return left.merge(right.drop(columns="pt_root_id"), on="_join_root_id", how="left").drop(
        columns="_join_root_id"
    )


def add_partner_annotations(client, partners):
    warnings = []
    partner_ids = [int(value) for value in partners["Partner ID"].tolist()]

    try:
        cell_types = client.materialize.tables.aibs_metamodel_celltypes_v661(
            pt_root_id=partner_ids
        ).query()
        if not cell_types.empty and "pt_root_id" in cell_types.columns:
            selected = [name for name in ["pt_root_id", "classification_system", "cell_type"] if name in cell_types]
            cell_types = cell_types[selected].drop_duplicates("pt_root_id", keep="last")
            partners = merge_root_annotations(partners, cell_types)
            partners = partners.rename(
                columns={"classification_system": "Cell class", "cell_type": "Cell type"}
            )
            if "Cell class" in partners:
                class_names = {
                    "excitatory_neuron": "Excitatory neuron",
                    "inhibitory_neuron": "Inhibitory neuron",
                    "nonneuron": "Non-neuronal",
                }
                partners["Cell class"] = partners["Cell class"].replace(class_names)
                partners["Cell class"] = partners["Cell class"].fillna("Unclassified")
            if "Cell type" in partners:
                partners["Cell type"] = partners["Cell type"].fillna("Unannotated")
    except Exception as exc:
        warnings.append(f"cell types ({type(exc).__name__})")

    try:
        proofreading = client.materialize.tables.proofreading_status_and_strategy(
            pt_root_id=partner_ids
        ).query()
        proof_columns = [
            "pt_root_id",
            "status_axon",
            "strategy_axon",
            "status_dendrite",
            "strategy_dendrite",
        ]
        if not proofreading.empty and "pt_root_id" in proofreading.columns:
            proofreading = proofreading[
                [name for name in proof_columns if name in proofreading.columns]
            ].drop_duplicates("pt_root_id", keep="last")
            partners = merge_root_annotations(partners, proofreading)
            partners = partners.rename(
                columns={
                    "status_axon": "Axon proofread",
                    "strategy_axon": "Axon strategy",
                    "status_dendrite": "Dendrite proofread",
                    "strategy_dendrite": "Dendrite strategy",
                }
            )
            for column in ["Axon proofread", "Dendrite proofread"]:
                if column in partners:
                    partners[column] = partners[column].map({True: "Yes", False: "No"}).fillna("Not available")
            for column in ["Axon strategy", "Dendrite strategy"]:
                if column in partners:
                    partners[column] = partners[column].fillna("Not available")
    except Exception as exc:
        warnings.append(f"proofreading ({type(exc).__name__})")

    return partners, warnings


def query_functional_properties(client, root_id, property_table):
    nuclei = client.materialize.tables.nucleus_detection_v0(pt_root_id=root_id).query()
    if nuclei.empty or "id" not in nuclei.columns:
        return pd.DataFrame()

    nucleus_ids = [int(value) for value in nuclei["id"].dropna().unique().tolist()]
    records = []
    for nucleus_id in nucleus_ids:
        table_query = getattr(client.materialize.tables, property_table)
        result = table_query(id=nucleus_id).query()
        if not result.empty:
            records.append(result)
    if not records:
        return pd.DataFrame()
    return pd.concat(records, ignore_index=True)


def build_comparison(primary_out, primary_in, comparison_out, comparison_in):
    pairs = [
        (primary_out, "post_pt_root_id", "A: output"),
        (primary_in, "pre_pt_root_id", "A: input"),
        (comparison_out, "post_pt_root_id", "B: output"),
        (comparison_in, "pre_pt_root_id", "B: input"),
    ]
    summary = None
    for synapses, partner_column, count_column in pairs:
        counts = summarize_direction(synapses, partner_column, count_column)
        summary = counts if summary is None else summary.merge(counts, on="Partner ID", how="outer")
    count_columns = ["A: output", "A: input", "B: output", "B: input"]
    summary[count_columns] = summary[count_columns].fillna(0).astype("int64")
    summary["Shared"] = (
        ((summary["A: output"] > 0) & (summary["B: output"] > 0))
        | ((summary["A: input"] > 0) & (summary["B: input"] > 0))
    ).map({True: "Yes", False: "No"})
    summary["A total"] = summary["A: output"] + summary["A: input"]
    summary["B total"] = summary["B: output"] + summary["B: input"]
    return summary.sort_values(["Shared", "A total", "B total"], ascending=[False, False, False])


def jaccard_overlap(primary, comparison, partner_column):
    primary_ids = set(primary[partner_column].dropna().tolist())
    comparison_ids = set(comparison[partner_column].dropna().tolist())
    union = primary_ids | comparison_ids
    return len(primary_ids & comparison_ids), (len(primary_ids & comparison_ids) / len(union) if union else 0.0)


def parse_root_ids(text):
    values = [part.strip() for part in text.replace(",", "\n").replace(";", "\n").splitlines()]
    ids = [int(value) for value in values if value]
    if not ids:
        raise ValueError("Enter at least one neuron root ID.")
    if len(ids) > 50:
        raise ValueError("Group analysis is limited to 50 neurons per run.")
    if len(set(ids)) != len(ids):
        raise ValueError("Remove duplicate neuron IDs from the group.")
    return ids


def analyze_group(client, root_ids, progress_callback=None):
    partner_rows = []
    neuron_rows = []
    for index, root_id in enumerate(root_ids, start=1):
        outgoing = client.materialize.synapse_query(pre_ids=root_id, remove_autapses=True)
        incoming = client.materialize.synapse_query(post_ids=root_id, remove_autapses=True)
        neuron_rows.append({
            "Neuron root ID": root_id,
            "Output synapses": len(outgoing),
            "Input synapses": len(incoming),
            "Unique output partners": outgoing["post_pt_root_id"].nunique() if "post_pt_root_id" in outgoing else 0,
            "Unique input partners": incoming["pre_pt_root_id"].nunique() if "pre_pt_root_id" in incoming else 0,
        })
        for frame, column, direction in [
            (outgoing, "post_pt_root_id", "Output"),
            (incoming, "pre_pt_root_id", "Input"),
        ]:
            if column not in frame:
                continue
            counts = frame.groupby(column).size()
            for partner_id, count in counts.items():
                partner_rows.append({"Neuron root ID": root_id, "Partner root ID": int(partner_id), "Direction": direction, "Synapses": int(count)})
        if progress_callback:
            progress_callback(index, len(root_ids), root_id)

    per_neuron = pd.DataFrame(neuron_rows)
    if partner_rows:
        edges = pd.DataFrame(partner_rows)
        partners = (edges.groupby(["Partner root ID", "Direction"], as_index=False)
                    .agg(**{"Group neurons connected": ("Neuron root ID", "nunique"),
                            "Total synapses": ("Synapses", "sum")}))
        partners["Group size"] = len(root_ids)
        partners["Connected fraction"] = partners["Group neurons connected"] / len(root_ids)
        partners = partners.sort_values(["Group neurons connected", "Total synapses"], ascending=False)
    else:
        partners = pd.DataFrame(columns=["Partner root ID", "Direction", "Group neurons connected", "Total synapses", "Group size", "Connected fraction"])
    return per_neuron, partners


st.set_page_config(page_title="MICrONS Connectome Explorer", page_icon="🧠", layout="wide")
st.title("MICrONS Connectome Explorer")
st.caption("Explore neuronal connectivity, cell annotations, visual-response summaries, and groups of neurons.")

with st.sidebar:
    st.header("Single-neuron query")
    saved_query_file = st.file_uploader("Load saved query settings (.json)", type=["json"])
    if st.button("Apply saved settings", disabled=saved_query_file is None):
        try:
            saved = json.load(saved_query_file)
            query = saved.get("query", saved)
            display = saved.get("display", {})
            st.session_state["root_id_input"] = str(query.get("root_id", EXAMPLE_ID))
            st.session_state["comparison_root_input"] = str(query.get("comparison_root_id") or "")
            st.session_state["group_ids_input"] = "\n".join(map(str, query.get("group_root_ids", [])))
            st.session_state["top_n_input"] = int(display.get("top_n", query.get("top_n", 25)))
            st.session_state["min_synapses_input"] = int(query.get("min_synapses", 1))
            st.session_state["annotations_input"] = bool(query.get("add_annotations", True))
            st.session_state["functional_match_input"] = query.get("functional_match", "Manual (higher confidence)")
            st.session_state["class_filter_input"] = display.get("class_filter", query.get("class_filter", "All"))
            st.session_state["proofreading_filter_input"] = display.get("proofreading_filter", query.get("proofreading_filter", "All"))
            st.session_state["cell_type_filter_input"] = display.get("cell_type_filter", query.get("cell_type_filter", ""))
            st.session_state["replay_materialization"] = saved.get("materialization")
            st.success("Settings loaded. Run the query or group analysis to repeat it.")
        except Exception as exc:
            st.error(f"Could not load this file ({type(exc).__name__}).")
    root_id_text = st.text_input("Neuron root ID (pt_root_id)", value=str(EXAMPLE_ID), key="root_id_input")
    comparison_root_text = st.text_input("Compare with another neuron (optional)", value="", key="comparison_root_input")
    top_n = st.slider("Partners to display", min_value=5, max_value=100, value=25, step=5, key="top_n_input")
    min_synapses = st.number_input("Minimum total synapses per partner", min_value=1, max_value=100, value=1, key="min_synapses_input")
    add_annotations = st.checkbox("Add cell type and proofreading annotations", value=True, key="annotations_input")
    class_filter = st.selectbox("Cell class", ["All", "Excitatory neuron", "Inhibitory neuron", "Non-neuronal", "Unclassified"], disabled=not add_annotations, key="class_filter_input")
    proofreading_filter = st.selectbox("Proofreading status", ["All", "Axon proofread", "Dendrite proofread", "Both proofread"], disabled=not add_annotations, key="proofreading_filter_input")
    cell_type_filter = st.text_input("Cell type contains", placeholder="e.g. BC or 23P", disabled=not add_annotations, key="cell_type_filter_input")
    functional_match = st.selectbox("Visual-response correspondence", ["Manual (higher confidence)", "Automated (more coverage)"], help="Automated matching has more coverage but is not manually verified.", key="functional_match_input")
    run_query = st.button("Run query", type="primary", use_container_width=True)
    st.divider()
    st.header("Group analysis")
    group_ids_text = st.text_area("Neuron root IDs (one per line, comma, or semicolon)", key="group_ids_input")
    run_group = st.button("Analyze group (up to 50 neurons)", use_container_width=True)

st.info("Queries use CAVE to retrieve synapses for each selected neuron.")
st.markdown("[Open MICrONS portal](https://www.microns-explorer.org/cortical-mm3) · [CAVE setup guide](https://tutorial.microns-explorer.org/quickstart_notebooks/01-caveclient-setup.html)")

if run_query:
    try:
        root_id = int(root_id_text.strip())
        comparison_root_id = int(comparison_root_text.strip()) if comparison_root_text.strip() else None
        if comparison_root_id == root_id:
            raise ValueError("The comparison ID must differ from the primary ID.")
        with st.spinner("Querying incoming and outgoing connections..."):
            client = CAVEclient(DATASTACK)
            replay_version = st.session_state.get("replay_materialization")
            if replay_version is not None:
                client.version = replay_version
            outgoing = client.materialize.synapse_query(pre_ids=root_id, remove_autapses=True)
            incoming = client.materialize.synapse_query(post_ids=root_id, remove_autapses=True)

            comparison_outgoing = pd.DataFrame()
            comparison_incoming = pd.DataFrame()
            comparison_partners = pd.DataFrame()
            comparison_metrics = None
            comparison_functional = pd.DataFrame()
            if comparison_root_id is not None:
                comparison_outgoing = client.materialize.synapse_query(
                    pre_ids=comparison_root_id, remove_autapses=True
                )
                comparison_incoming = client.materialize.synapse_query(
                    post_ids=comparison_root_id, remove_autapses=True
                )
                comparison_partners = build_comparison(
                    outgoing, incoming, comparison_outgoing, comparison_incoming
                )
                comparison_partners = comparison_partners[
                    (comparison_partners["A total"] + comparison_partners["B total"]) >= min_synapses
                ].reset_index(drop=True)
                if add_annotations and not comparison_partners.empty:
                    comparison_partners, _ = add_partner_annotations(client, comparison_partners)

            partners = summarize_direction(outgoing, "post_pt_root_id", "Output synapses")
            incoming_partners = summarize_direction(incoming, "pre_pt_root_id", "Input synapses")
            partners = partners.merge(incoming_partners, on="Partner ID", how="outer")
            partners[["Output synapses", "Input synapses"]] = partners[
                ["Output synapses", "Input synapses"]
            ].fillna(0).astype("int64")
            partners["Total synapses"] = partners["Output synapses"] + partners["Input synapses"]
            partners = partners[partners["Total synapses"] >= min_synapses]
            partners = partners.sort_values("Total synapses", ascending=False).reset_index(drop=True)

            annotation_warnings = []
            if add_annotations and not partners.empty:
                partners, annotation_warnings = add_partner_annotations(client, partners)

            functional_table = (
                "digital_twin_properties_bcm_coreg_v4"
                if functional_match == "Manual (higher confidence)"
                else "digital_twin_properties_bcm_coreg_auto_phase3_fwd_v2"
            )
            functional_properties = pd.DataFrame()
            functional_warning = None
            try:
                functional_properties = query_functional_properties(client, root_id, functional_table)
            except Exception as exc:
                functional_warning = type(exc).__name__
            comparison_functional_warning = None
            if comparison_root_id is not None:
                try:
                    comparison_functional = query_functional_properties(
                        client, comparison_root_id, functional_table
                    )
                except Exception as exc:
                    comparison_functional_warning = type(exc).__name__

                comparison_metrics = {
                    "common_outgoing": len(
                        set(outgoing["post_pt_root_id"].dropna())
                        & set(comparison_outgoing["post_pt_root_id"].dropna())
                    ),
                    "common_incoming": len(
                        set(incoming["pre_pt_root_id"].dropna())
                        & set(comparison_incoming["pre_pt_root_id"].dropna())
                    ),
                    "outgoing_jaccard": jaccard_overlap(
                        outgoing, comparison_outgoing, "post_pt_root_id"
                    )[1],
                    "incoming_jaccard": jaccard_overlap(
                        incoming, comparison_incoming, "pre_pt_root_id"
                    )[1],
                }

        st.session_state["all_partners"] = partners
        st.session_state["query_meta"] = {
            "root_id": root_id,
            "total_synapses": len(outgoing) + len(incoming),
            "materialization": getattr(client, "version", "latest public version"),
            "outgoing_count": len(outgoing),
            "incoming_count": len(incoming),
        }
        st.session_state["query_settings"] = {
            "top_n": int(top_n),
            "min_synapses": int(min_synapses),
            "add_annotations": bool(add_annotations),
            "functional_match": functional_match,
        }
        st.session_state["annotation_warnings"] = annotation_warnings
        st.session_state["functional_properties"] = functional_properties
        st.session_state["functional_warning"] = functional_warning
        st.session_state["functional_match"] = functional_match
        st.session_state["comparison_root_id"] = comparison_root_id
        st.session_state["comparison_partners"] = comparison_partners
        st.session_state["comparison_metrics"] = comparison_metrics
        st.session_state["comparison_functional"] = comparison_functional
        st.session_state["comparison_functional_warning"] = comparison_functional_warning
    except ValueError:
        st.error("The ID must be an integer (pt_root_id).")
    except Exception as exc:
        st.error("The query failed. Check your CAVE token and internet connection.")
        st.caption(f"Technical detail: {type(exc).__name__}")

if run_group:
    try:
        group_root_ids = parse_root_ids(group_ids_text)
        with st.spinner(f"Querying synapses for {len(group_root_ids)} neurons..."):
            group_client = CAVEclient(DATASTACK)
            replay_version = st.session_state.get("replay_materialization")
            if replay_version is not None:
                group_client.version = replay_version
            group_progress = st.progress(0, text="Starting group analysis...")

            def update_group_progress(completed, total, root_id):
                group_progress.progress(
                    completed / total,
                    text=f"Queried neuron {completed} of {total} · {root_id}",
                )

            group_per_neuron, group_partners = analyze_group(
                group_client, group_root_ids, progress_callback=update_group_progress
            )
            group_materialization = getattr(group_client, "version", "latest public version")
        st.session_state["group_per_neuron"] = group_per_neuron
        st.session_state["group_partners"] = group_partners
        st.session_state["group_meta"] = {"root_ids": group_root_ids, "materialization": group_materialization}
    except ValueError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error("Group analysis failed. Check your CAVE token and internet connection.")
        st.caption(f"Technical detail: {type(exc).__name__}")

if "all_partners" in st.session_state:
    meta = st.session_state["query_meta"]
    partners = st.session_state["all_partners"].copy()

    if add_annotations and class_filter != "All" and "Cell class" in partners:
        partners = partners[partners["Cell class"] == class_filter]
    if add_annotations and proofreading_filter != "All":
        if proofreading_filter in ["Axon proofread", "Both proofread"] and "Axon proofread" in partners:
            partners = partners[partners["Axon proofread"] == "Yes"]
        if proofreading_filter in ["Dendrite proofread", "Both proofread"] and "Dendrite proofread" in partners:
            partners = partners[partners["Dendrite proofread"] == "Yes"]
    if add_annotations and cell_type_filter.strip() and "Cell type" in partners:
        partners = partners[
            partners["Cell type"].str.contains(cell_type_filter.strip(), case=False, na=False)
        ]

    partners = partners.sort_values("Total synapses", ascending=False)
    filtered_count = len(partners)
    shown_partners = partners.head(top_n).reset_index(drop=True)

    a, b, c = st.columns(3)
    a.metric("Synapses queried", f"{meta['total_synapses']:,}")
    b.metric("Partners after filters", filtered_count)
    c.metric("Partners shown", len(shown_partners))
    st.caption(
        f"Neuron {meta['root_id']} · datastack {DATASTACK} · "
        f"materialization {meta['materialization']} · "
        f"outputs {meta['outgoing_count']:,} / inputs {meta['incoming_count']:,}"
    )
    query_settings = st.session_state.get("query_settings", {})
    query_manifest = {
        "format": "microns-mouse-tool-query-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "datastack": DATASTACK,
        "materialization": meta["materialization"],
        "query": {
            "root_id": int(meta["root_id"]),
            "comparison_root_id": st.session_state.get("comparison_root_id"),
            "group_root_ids": [],
            **query_settings,
        },
        "display": {
            "top_n": int(top_n),
            "class_filter": class_filter,
            "proofreading_filter": proofreading_filter,
            "cell_type_filter": cell_type_filter,
        },
    }
    st.download_button(
        "Save query settings and provenance (.json)",
        data=json.dumps(query_manifest, indent=2).encode("utf-8"),
        file_name=f"microns_query_{meta['root_id']}.json",
        mime="application/json",
    )

    st.subheader("Visual response")
    st.caption(f"Correspondence {st.session_state.get('functional_match', functional_match).lower()} between visual record and reconstructed neuron.")
    functional_warning = st.session_state.get("functional_warning")
    functional_properties = st.session_state.get("functional_properties", pd.DataFrame())
    if functional_warning:
        st.warning(f"Could not retrieve visual-response properties ({functional_warning}).")
    else:
        if functional_properties.empty:
            st.info(
                "No visual record was found for this neuron using the selected correspondence. "
                "Try automated matching or query another neuron."
            )
        else:
            functional_columns = [
                "session",
                "scan_idx",
                "unit_id",
                "pref_ori",
                "pref_dir",
                "OSI",
                "DSI",
                "gOSI",
                "gDSI",
                "cc_abs",
                "cc_norm",
                "residual",
                "score",
            ]
            functional_columns = [column for column in functional_columns if column in functional_properties.columns]
            functional_table_view = functional_properties[functional_columns].copy()
            if "cc_abs" in functional_table_view.columns:
                functional_table_view = functional_table_view.sort_values("cc_abs", ascending=False)
            functional_table_view = functional_table_view.rename(
                columns={
                    "session": "Session",
                    "scan_idx": "Scan",
                    "unit_id": "Unit",
                    "pref_ori": "Preferred orientation (°)",
                    "pref_dir": "Preferred direction (°)",
                    "OSI": "Orientation selectivity (OSI)",
                    "DSI": "Direction selectivity (DSI)",
                    "gOSI": "Global orientation selectivity",
                    "gDSI": "Global direction selectivity",
                    "cc_abs": "Model fit (cc_abs)",
                    "cc_norm": "Normalized fit (cc_norm)",
                    "residual": "Correspondence error (µm)",
                    "score": "Correspondence distance (µm)",
                }
            )
            st.dataframe(functional_table_view, hide_index=True, use_container_width=True)
            st.caption(
                "Preferred orientation is the visual pattern angle; preferred direction indicates its motion direction. "
                "All matching records are shown. These measures describe modeled responses, not a live recording."
            )

        visual_points = []
        response_sets = [("Neuron A", functional_properties)]
        if st.session_state.get("comparison_root_id") is not None:
            response_sets.append(("Neuron B", st.session_state.get("comparison_functional", pd.DataFrame())))
        for neuron_label, response_table in response_sets:
            if response_table.empty or "pref_ori" not in response_table.columns:
                continue
            strength_column = "gOSI" if "gOSI" in response_table.columns else "OSI"
            if strength_column not in response_table.columns:
                continue
            points = response_table[["pref_ori", strength_column]].copy()
            points = points.rename(
                columns={"pref_ori": "Preferred orientation (°)", strength_column: "Selectivity"}
            )
            points["Neuron"] = neuron_label
            visual_points.append(points)
        if visual_points:
            st.markdown("**Visual summary**")
            st.scatter_chart(
                pd.concat(visual_points, ignore_index=True),
                x="Preferred orientation (°)",
                y="Selectivity",
                color="Neuron",
                x_label="Preferred orientation (degrees)",
                y_label="Orientation selectivity",
            )
            st.caption(
                "Each point is a functional record. The plot compares preferred orientation and selectivity; "
                "it is not a full response curve across stimuli."
            )

    comparison_root_id = st.session_state.get("comparison_root_id")
    comparison_export = pd.DataFrame()
    if comparison_root_id is not None:
        st.subheader("Compare connectivity with another neuron")
        comparison_metrics = st.session_state["comparison_metrics"]
        metrics_cols = st.columns(4)
        metrics_cols[0].metric("Shared output partners", comparison_metrics["common_outgoing"])
        metrics_cols[1].metric("Output overlap", f"{comparison_metrics['outgoing_jaccard']:.0%}")
        metrics_cols[2].metric("Shared input partners", comparison_metrics["common_incoming"])
        metrics_cols[3].metric("Input overlap", f"{comparison_metrics['incoming_jaccard']:.0%}")
        st.caption(
            f"A = {meta['root_id']} · B = {comparison_root_id}. "
            "The percentage measures overlap between partner lists in each direction."
        )

        comparison_view = st.session_state["comparison_partners"].copy()
        if add_annotations and class_filter != "All" and "Cell class" in comparison_view:
            comparison_view = comparison_view[comparison_view["Cell class"] == class_filter]
        if add_annotations and proofreading_filter != "All":
            if proofreading_filter in ["Axon proofread", "Both proofread"] and "Axon proofread" in comparison_view:
                comparison_view = comparison_view[comparison_view["Axon proofread"] == "Yes"]
            if proofreading_filter in ["Dendrite proofread", "Both proofread"] and "Dendrite proofread" in comparison_view:
                comparison_view = comparison_view[comparison_view["Dendrite proofread"] == "Yes"]
        if add_annotations and cell_type_filter.strip() and "Cell type" in comparison_view:
            comparison_view = comparison_view[
                comparison_view["Cell type"].str.contains(cell_type_filter.strip(), case=False, na=False)
            ]
        comparison_view = comparison_view.sort_values(
            ["Shared", "A total", "B total"], ascending=[False, False, False]
        ).head(top_n)
        comparison_export = comparison_view
        if comparison_view.empty:
            st.warning("No partners matched those filters.")
        else:
            st.dataframe(comparison_view, hide_index=True, use_container_width=True)
            st.download_button(
                "Download comparison CSV",
                data=comparison_view.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"microns_comparacion_{meta['root_id']}_{comparison_root_id}.csv",
                mime="text/csv",
            )

    st.subheader("3D view")
    st.caption(
        "Create a Neuroglancer link showing this neuron and its incoming and outgoing synapses. "
        "The link stores a view state on the public MICrONS service."
    )
    if st.button("Generate 3D view", type="secondary"):
        try:
            from nglui.statebuilder import helpers

            with st.spinner("Preparing the Neuroglancer view..."):
                viewer_client = CAVEclient(DATASTACK)
                if isinstance(meta["materialization"], int):
                    viewer_client.version = meta["materialization"]
                st.session_state["neuroglancer_url"] = helpers.make_neuron_neuroglancer_link(
                    viewer_client,
                    int(meta["root_id"]),
                    show_inputs=True,
                    show_outputs=True,
                    shorten=True,
                    return_as="url",
                )
        except Exception as exc:
            st.error("Could not generate the Neuroglancer link.")
            st.caption(f"Technical detail: {type(exc).__name__}")

    if st.session_state.get("neuroglancer_url"):
        st.link_button("Open 3D view in Neuroglancer", st.session_state["neuroglancer_url"])

    if st.session_state.get("annotation_warnings"):
        st.warning(
            "Some annotations could not be loaded: "
            + ", ".join(st.session_state["annotation_warnings"])
            + ". The connectivity table is still available."
        )

    if shown_partners.empty:
        st.warning("No partners match the selected filters.")
    else:
        st.subheader("Neuron connectivity")
        st.caption(
            "Each row is a partner. The two columns show synapses in each direction; "
            "the total is used to rank partners."
        )
        st.dataframe(shown_partners, hide_index=True, use_container_width=True)
        st.download_button(
            "Download results CSV",
            data=shown_partners.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"microns_connectivity_{meta['root_id']}.csv",
            mime="text/csv",
        )
    export_tables = {
        "connectivity.csv": partners,
        "visual_response.csv": st.session_state.get("functional_properties", pd.DataFrame()),
        "comparison.csv": comparison_export,
    }
    st.download_button(
        "Download complete analysis bundle (.zip)",
        data=build_export_bundle(query_manifest, export_tables),
        file_name=f"microns_analysis_{meta['root_id']}.zip",
        mime="application/zip",
        help="Includes CSV result tables, query settings, and the selected MICrONS materialization.",
    )
    st.caption(
        "Synapses provide anatomical evidence; their count is not a direct measure of functional strength. "
        "Proofreading status indicates which parts of the reconstruction were reviewed."
    )

if "group_per_neuron" in st.session_state:
    group_meta = st.session_state["group_meta"]
    st.header("Group analysis results")
    st.caption(f"{len(group_meta['root_ids'])} neurons · datastack {DATASTACK} · materialization {group_meta['materialization']}")
    group_manifest = {"format": "microns-mouse-tool-query-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                      "datastack": DATASTACK, "materialization": group_meta["materialization"],
                      "query": {"root_id": group_meta["root_ids"][0], "group_root_ids": group_meta["root_ids"],
                                "comparison_root_id": None, "top_n": int(top_n), "min_synapses": int(min_synapses),
                                "add_annotations": bool(add_annotations), "functional_match": functional_match,
                                "class_filter": class_filter, "proofreading_filter": proofreading_filter,
                                "cell_type_filter": cell_type_filter}}
    st.download_button("Save group query settings and provenance (.json)", json.dumps(group_manifest, indent=2).encode("utf-8"),
                       file_name="microns_group_query.json", mime="application/json", key="save_group_query")
    st.subheader("Per-neuron summary")
    st.dataframe(st.session_state["group_per_neuron"], hide_index=True, use_container_width=True)
    st.download_button("Download per-neuron summary (.csv)", st.session_state["group_per_neuron"].to_csv(index=False).encode("utf-8-sig"),
                       file_name="microns_group_neurons.csv", mime="text/csv", key="group_neurons_csv")
    st.subheader("Partners across the group")
    st.caption("Counts show how many queried neurons connect to each partner. Input and output are summarized separately.")
    group_partners_view = st.session_state["group_partners"].copy()
    if not group_partners_view.empty:
        group_partners_view = group_partners_view[group_partners_view["Total synapses"] >= min_synapses].head(top_n)
    st.dataframe(group_partners_view, hide_index=True, use_container_width=True)
    st.download_button("Download group partner summary (.csv)", group_partners_view.to_csv(index=False).encode("utf-8-sig"),
                       file_name="microns_group_partners.csv", mime="text/csv", key="group_partners_csv")
    st.download_button(
        "Download complete group bundle (.zip)",
        data=build_export_bundle(
            group_manifest,
            {
                "per_neuron.csv": st.session_state["group_per_neuron"],
                "group_partners.csv": group_partners_view,
            },
        ),
        file_name="microns_group_analysis.zip",
        mime="application/zip",
        help="Includes group result tables, the neuron IDs, filters, and selected MICrONS materialization.",
        key="group_analysis_bundle",
    )
