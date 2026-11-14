import streamlit as st
import pandas as pd
from caveclient import CAVEclient


DATASTACK = "minnie65_public"
EXAMPLE_ID = 864691136968109774


def summarize_direction(synapses, partner_column, result_column):
    if synapses.empty:
        return pd.DataFrame(
            {"ID socio": pd.Series(dtype="uint64"), result_column: pd.Series(dtype="int64")}
        )
    return (
        synapses.groupby(partner_column, as_index=False)
        .size()
        .rename(columns={partner_column: "ID socio", "size": result_column})
    )


def merge_root_annotations(partners, annotations):
    left = partners.copy()
    right = annotations.copy()
    left["_join_root_id"] = left["ID socio"].astype("string")
    right["_join_root_id"] = right["pt_root_id"].astype("string")
    return left.merge(right.drop(columns="pt_root_id"), on="_join_root_id", how="left").drop(
        columns="_join_root_id"
    )


def add_partner_annotations(client, partners):
    warnings = []
    partner_ids = [int(value) for value in partners["ID socio"].tolist()]

    try:
        cell_types = client.materialize.tables.aibs_metamodel_celltypes_v661(
            pt_root_id=partner_ids
        ).query()
        if not cell_types.empty and "pt_root_id" in cell_types.columns:
            selected = [name for name in ["pt_root_id", "classification_system", "cell_type"] if name in cell_types]
            cell_types = cell_types[selected].drop_duplicates("pt_root_id", keep="last")
            partners = merge_root_annotations(partners, cell_types)
            partners = partners.rename(
                columns={"classification_system": "Clase celular", "cell_type": "Tipo celular"}
            )
            if "Clase celular" in partners:
                class_names = {
                    "excitatory_neuron": "Neurona excitatoria",
                    "inhibitory_neuron": "Neurona inhibitoria",
                    "nonneuron": "No neuronal",
                }
                partners["Clase celular"] = partners["Clase celular"].replace(class_names)
                partners["Clase celular"] = partners["Clase celular"].fillna("Sin clasificación")
            if "Tipo celular" in partners:
                partners["Tipo celular"] = partners["Tipo celular"].fillna("Sin anotación")
    except Exception as exc:
        warnings.append(f"tipos celulares ({type(exc).__name__})")

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
                    "status_axon": "Axón revisado",
                    "strategy_axon": "Estrategia del axón",
                    "status_dendrite": "Dendrita revisada",
                    "strategy_dendrite": "Estrategia de la dendrita",
                }
            )
            for column in ["Axón revisado", "Dendrita revisada"]:
                if column in partners:
                    partners[column] = partners[column].map({True: "Sí", False: "No"}).fillna("Sin dato")
            for column in ["Estrategia del axón", "Estrategia de la dendrita"]:
                if column in partners:
                    partners[column] = partners[column].fillna("Sin dato")
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


st.set_page_config(page_title="MICrONS · Conexiones", page_icon="🧠", layout="wide")
st.title("MICrONS · Explorador de conexiones")
st.caption("Explora conexiones de entrada y salida, con anotaciones del conectoma del ratón.")

with st.sidebar:
    st.header("Consulta")
    root_id_text = st.text_input("ID de neurona (pt_root_id)", value=str(EXAMPLE_ID))
    top_n = st.slider("Mostrar socios", min_value=5, max_value=100, value=25, step=5)
    min_synapses = st.number_input("Mínimo de sinapsis totales por socio", min_value=1, max_value=100, value=1)
    add_annotations = st.checkbox(
        "Añadir tipo celular y proofreading",
        value=True,
        help="Consulta las anotaciones para los socios de esta neurona.",
    )
    class_filter = st.selectbox(
        "Clase celular",
        [
            "Todas",
            "Neurona excitatoria",
            "Neurona inhibitoria",
            "No neuronal",
            "Sin clasificación",
        ],
        disabled=not add_annotations,
    )
    proofreading_filter = st.selectbox(
        "Estado de proofreading",
        ["Todos", "Axón revisado", "Dendrita revisada", "Ambos revisados"],
        disabled=not add_annotations,
    )
    cell_type_filter = st.text_input(
        "Tipo celular contiene",
        placeholder="por ejemplo BC o 23P",
        disabled=not add_annotations,
    )
    functional_match = st.selectbox(
        "Enlace con actividad visual",
        ["Manual (más confiable)", "Automático (más cobertura)"],
        help="La correspondencia automática puede incluir más neuronas, pero no fue revisada manualmente.",
    )
    run_query = st.button("Consultar MICrONS", type="primary", use_container_width=True)

st.info("La consulta usa CAVE y descarga solo las sinapsis de la neurona seleccionada.")
st.markdown(
    "[Abrir portal MICrONS](https://www.microns-explorer.org/cortical-mm3) · "
    "[Cómo configurar CAVE](https://tutorial.microns-explorer.org/quickstart_notebooks/01-caveclient-setup.html)"
)

if run_query:
    try:
        root_id = int(root_id_text.strip())
        with st.spinner("Consultando conexiones de entrada y salida…"):
            client = CAVEclient(DATASTACK)
            outgoing = client.materialize.synapse_query(pre_ids=root_id, remove_autapses=True)
            incoming = client.materialize.synapse_query(post_ids=root_id, remove_autapses=True)

            partners = summarize_direction(outgoing, "post_pt_root_id", "Sinapsis de salida")
            incoming_partners = summarize_direction(incoming, "pre_pt_root_id", "Sinapsis de entrada")
            partners = partners.merge(incoming_partners, on="ID socio", how="outer")
            partners[["Sinapsis de salida", "Sinapsis de entrada"]] = partners[
                ["Sinapsis de salida", "Sinapsis de entrada"]
            ].fillna(0).astype("int64")
            partners["Sinapsis totales"] = partners["Sinapsis de salida"] + partners["Sinapsis de entrada"]
            partners = partners[partners["Sinapsis totales"] >= min_synapses]
            partners = partners.sort_values("Sinapsis totales", ascending=False).reset_index(drop=True)

            annotation_warnings = []
            if add_annotations and not partners.empty:
                partners, annotation_warnings = add_partner_annotations(client, partners)

            functional_table = (
                "digital_twin_properties_bcm_coreg_v4"
                if functional_match == "Manual (más confiable)"
                else "digital_twin_properties_bcm_coreg_auto_phase3_fwd_v2"
            )
            functional_properties = pd.DataFrame()
            functional_warning = None
            try:
                functional_properties = query_functional_properties(client, root_id, functional_table)
            except Exception as exc:
                functional_warning = type(exc).__name__

        st.session_state["all_partners"] = partners
        st.session_state["query_meta"] = {
            "root_id": root_id,
            "total_synapses": len(outgoing) + len(incoming),
            "materialization": getattr(client, "version", "última versión pública"),
            "outgoing_count": len(outgoing),
            "incoming_count": len(incoming),
        }
        st.session_state["annotation_warnings"] = annotation_warnings
        st.session_state["functional_properties"] = functional_properties
        st.session_state["functional_warning"] = functional_warning
        st.session_state["functional_match"] = functional_match
    except ValueError:
        st.error("El ID debe ser un número entero (pt_root_id).")
    except Exception as exc:
        st.error("No se pudo completar la consulta. Comprueba el token de CAVE y la conexión a internet.")
        st.caption(f"Detalle técnico: {type(exc).__name__}")

if "all_partners" in st.session_state:
    meta = st.session_state["query_meta"]
    partners = st.session_state["all_partners"].copy()

    if add_annotations and class_filter != "Todas" and "Clase celular" in partners:
        partners = partners[partners["Clase celular"] == class_filter]
    if add_annotations and proofreading_filter != "Todos":
        if proofreading_filter in ["Axón revisado", "Ambos revisados"] and "Axón revisado" in partners:
            partners = partners[partners["Axón revisado"] == "Sí"]
        if proofreading_filter in ["Dendrita revisada", "Ambos revisados"] and "Dendrita revisada" in partners:
            partners = partners[partners["Dendrita revisada"] == "Sí"]
    if add_annotations and cell_type_filter.strip() and "Tipo celular" in partners:
        partners = partners[
            partners["Tipo celular"].str.contains(cell_type_filter.strip(), case=False, na=False)
        ]

    partners = partners.sort_values("Sinapsis totales", ascending=False)
    filtered_count = len(partners)
    shown_partners = partners.head(top_n).reset_index(drop=True)

    a, b, c = st.columns(3)
    a.metric("Sinapsis consultadas", f"{meta['total_synapses']:,}")
    b.metric("Socios tras filtros", filtered_count)
    c.metric("Socios mostrados", len(shown_partners))
    st.caption(
        f"Neurona {meta['root_id']} · datastack {DATASTACK} · "
        f"materialización {meta['materialization']} · "
        f"salidas {meta['outgoing_count']:,} / entradas {meta['incoming_count']:,}"
    )

    st.subheader("Respuesta visual")
    st.caption(f"Correspondencia {st.session_state.get('functional_match', functional_match).lower()} entre registro visual y neurona reconstruida.")
    functional_warning = st.session_state.get("functional_warning")
    functional_properties = st.session_state.get("functional_properties", pd.DataFrame())
    if functional_warning:
        st.warning(f"No se pudieron consultar las propiedades visuales ({functional_warning}).")
    elif functional_properties.empty:
        st.info(
            "No encontramos un registro visual asociado con esta neurona usando la correspondencia seleccionada. "
            "Prueba la opción automática o consulta otra neurona."
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
                "session": "Sesión",
                "scan_idx": "Escaneo",
                "unit_id": "Registro",
                "pref_ori": "Orientación preferida (°)",
                "pref_dir": "Dirección preferida (°)",
                "OSI": "Selectividad de orientación (OSI)",
                "DSI": "Selectividad de dirección (DSI)",
                "gOSI": "Selectividad global de orientación",
                "gDSI": "Selectividad global de dirección",
                "cc_abs": "Ajuste del modelo (cc_abs)",
                "cc_norm": "Ajuste normalizado (cc_norm)",
                "residual": "Error de correspondencia (µm)",
                "score": "Separación de correspondencia (µm)",
            }
        )
        st.dataframe(functional_table_view, hide_index=True, use_container_width=True)
        st.caption(
            "La orientación preferida indica el ángulo de patrón visual; la dirección preferida indica hacia dónde se mueve. "
            "Si hay varios registros, se muestran todos. Las medidas describen la respuesta modelada, no una grabación en vivo."
        )

    st.subheader("Vista tridimensional")
    st.caption(
        "Genera un enlace de Neuroglancer con la neurona y sus sinapsis de entrada y salida. "
        "El enlace guarda un estado visual en el servicio público de MICrONS."
    )
    if st.button("Generar vista 3D", type="secondary"):
        try:
            from nglui.statebuilder import helpers

            with st.spinner("Preparando la vista en Neuroglancer…"):
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
            st.error("No se pudo generar el enlace de Neuroglancer.")
            st.caption(f"Detalle técnico: {type(exc).__name__}")

    if st.session_state.get("neuroglancer_url"):
        st.link_button("Abrir vista 3D en Neuroglancer", st.session_state["neuroglancer_url"])

    if st.session_state.get("annotation_warnings"):
        st.warning(
            "No se pudieron cargar algunas anotaciones: "
            + ", ".join(st.session_state["annotation_warnings"])
            + ". La tabla de conexiones sigue disponible."
        )

    if shown_partners.empty:
        st.warning("No hay socios que coincidan con los filtros.")
    else:
        st.subheader("Red alrededor de la neurona")
        st.caption(
            "Cada fila es un socio. Las dos columnas muestran sinapsis en cada sentido; "
            "el total se usa para ordenar la lista."
        )
        st.dataframe(shown_partners, hide_index=True, use_container_width=True)
        st.download_button(
            "Descargar resultados CSV",
            data=shown_partners.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"microns_red_{meta['root_id']}.csv",
            mime="text/csv",
        )
    st.caption(
        "Las sinapsis son evidencia anatómica; su cantidad no equivale directamente a fuerza funcional. "
        "El estado de proofreading indica qué partes de la reconstrucción fueron revisadas."
    )
