import hashlib,json,csv,io
from pathlib import Path
import streamlit as st
import pandas as pd
from fusion import reconcile,enrich,csv_bytes,ConversionError
# Versioned session data: old export tuples must never survive a schema change.
CACHE_SCHEMA = 'fec-enrichi-accounts-v3'
REQUIRED_REPORT = {'source_rows','output_rows','accounts_promoted','lettered_rows',
                   'unresolved','aux_labels_missing','analytic_discrepancies','output_base_columns'}

def normalize_export(raw,result,rows,fields,report):
    # Compatible with the previous fusion.py: derive account data from the source,
    # not missing report keys and not a potentially stale already-collapsed export.
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:text=raw.decode('cp1252')
    sep='\t' if '\t' in text.splitlines()[0] else ';'
    source=list(csv.DictReader(io.StringIO(text),delimiter=sep))
    if len(source)!=len(result[0]):raise ConversionError('Nombre de lignes source incohérent.')
    by_id={f'FEC-{parsed["_line"]:07d}':original for parsed,original in zip(result[0],source)}
    headers=list(source[0])
    for row in rows:
        original=by_id.get(row.get('IdentifiantLigneSource'))
        if original is None:raise ConversionError('Version du moteur incompatible : mettez à jour fusion.py.')
        aux=original.get('CompAuxNum','') or ''
        row['CompteNum']=aux if aux.strip() else original['CompteNum']
        aux_label=original.get('CompAuxLib','') or ''
        row['CompteLib']=aux_label if aux.strip() and aux_label.strip() else (original.get('CompteLib','') or '')
        row.pop('CompAuxNum',None);row.pop('CompAuxLib',None)
        for name in headers:
            if name not in ('CompteNum','CompteLib','CompAuxNum','CompAuxLib') and row.get(name)!=original[name]:
                raise ConversionError('Une colonne FEC a changé : régénérez avec les fichiers source.')
    fields=[k for k in fields if k not in ('CompAuxNum','CompAuxLib')]
    if 'CompteLib' not in fields:fields.insert(fields.index('CompteNum')+1,'CompteLib')
    base=[k for k in headers if k not in ('CompAuxNum','CompAuxLib')]
    if 'CompteLib' not in base:base.append('CompteLib')
    report=dict(report)
    report.update(source_rows=len(source),output_rows=len(rows),
        accounts_promoted=sum(bool((r.get('CompAuxNum') or '').strip()) for r in source),
        aux_labels_missing=sum(bool((r.get('CompAuxNum') or '').strip()) and not (r.get('CompAuxLib') or '').strip() for r in source),
        lettered_rows=sum(bool((r.get('EcritureLet') or '').strip()) for r in source),
        unresolved=len(result[4]),output_base_columns=len(base))
    if 'analytic_discrepancies' not in report:
        report['analytic_discrepancies']=len({r['IdentifiantLigneSource'] for r in rows if 'ÉCART ANALYTIQUE' in r.get('StatutRapprochement','')})
    return rows,fields,report,csv_bytes(rows,fields)

def valid_export(value):
    return (isinstance(value,(tuple,list)) and len(value)==4
            and isinstance(value[2],dict) and REQUIRED_REPORT <= value[2].keys()
            and 'CompAuxNum' not in value[1] and 'CompAuxLib' not in value[1])

st.set_page_config(page_title='FEC enrichi avec analytique',page_icon='📑',layout='wide')
st.title('Ton FEC complet + l’analytique')
st.caption('Version corrigée : comptes uniques · cache v3')
st.write('Un seul compte et son libellé : l’auxiliaire est prioritaire sur le collectif. Dates, journaux, lettrage, références et montants sont conservés ; l’analytique est ajoutée.')
with st.sidebar:
    ff=st.file_uploader('FEC initial',type=['txt','csv','fec'])
    pp=st.file_uploader('PNM avec analytique',type=['pnm','txt'])
    enc=st.selectbox('Encodage PNM',['cp850','cp1252','utf-8-sig'])
    family=st.text_input('Nom de la famille analytique','Plan 1')
    mode=st.radio('Organisation des lignes',['Une ligne par ligne du FEC','Une ligne par catégorie analytique'])
    st.caption('1 ligne d’en-tête dans chaque fichier. Aucun envoi à Pennylane.')
if not ff or not pp:st.stop()
raw=ff.getvalue();pnm=pp.getvalue()
engine_path=Path(__file__).with_name('fusion.py')
engine_hash=hashlib.sha256(engine_path.read_bytes()).hexdigest() if engine_path.exists() else 'embedded'
schema_key=(CACHE_SCHEMA,engine_hash)
if st.session_state.get('_cache_schema')!=schema_key:
    for stale in ('source_key','result','export_key','export'):
        st.session_state.pop(stale,None)
    st.session_state['_cache_schema']=schema_key
key=hashlib.sha256(raw+pnm+enc.encode()).hexdigest()
try:
    if st.session_state.get('source_key')!=key or 'result' not in st.session_state:
        with st.spinner('Rapprochement des deux fichiers…'):
            result=reconcile(raw,pnm,enc)
        st.session_state['result']=result;st.session_state['source_key']=key
    result=st.session_state['result']
    ek=(schema_key,key,family,mode)
    if st.session_state.get('export_key')!=ek or not valid_export(st.session_state.get('export')):
        rows,fields,report=enrich(raw,result,family,'original' if mode.startswith('Une ligne par ligne') else 'categories')
        st.session_state['export']=normalize_export(raw,result,rows,fields,report);st.session_state['export_key']=ek
    rows,fields,report,content=st.session_state['export']
except (ConversionError,ValueError) as e:st.error(str(e));st.stop()
a,b,c,d=st.columns(4)
a.metric('Lignes du FEC',report['source_rows']);b.metric('Comptes auxiliaires repris',report['accounts_promoted']);c.metric('Lignes avec lettrage conservé',report['lettered_rows']);d.metric('À rapprocher',report['unresolved'])
st.success('CompteNum et CompteLib sont les seules colonnes de compte et de libellé de compte. CompAuxNum et CompAuxLib ont été fusionnées puis supprimées de l’export.')
if report['aux_labels_missing']:st.caption(f"{report['aux_labels_missing']} auxiliaires n’ont pas de libellé : le libellé du compte général est conservé en remplacement.")
if report['unresolved']:st.warning(f"{report['unresolved']} correspondances sont ambiguës. Les ajouts concernés restent vides ; les candidats et leur analytique sont conservés dans CandidatsPNM, dans le même fichier. Aucun choix au hasard.")
if report['analytic_discrepancies']:st.caption(f"{report['analytic_discrepancies']} écarts analytiques source sont signalés. Cette version ne normalise et ne corrige aucun montant.")
if mode.startswith('Une ligne par ligne'):
    st.caption('Plusieurs catégories sur une ligne : valeurs séparées par |, dans le même ordre pour famille, catégorie, poids et montant. Pour mapper une seule catégorie par ligne, choisir le second mode.')
else:st.warning('Les lignes multi-catégories répètent les colonnes du FEC. Mapper IdentifiantLigneSource pour regrouper les répétitions ; ne pas sommer les montants sans dédupliquer cet identifiant.')
with st.expander('Voir les colonnes conservées et ajoutées'):
    st.write('**Colonnes FEC :** '+', '.join(fields[:report['output_base_columns']]))
    st.write('**Colonnes ajoutées :** '+', '.join(fields[report['output_base_columns']:]))
st.subheader('Aperçu')
search=st.text_input('Rechercher une facture, un compte, une date AAAAMMJJ ou un libellé')
view=[r for r in rows if search.casefold() in ' '.join(str(v) for k,v in r.items() if k not in ['DetailAnalytiquePNM','CandidatsPNM']).casefold()] if search else rows
st.dataframe(pd.DataFrame(view[:300],columns=fields),hide_index=True,width='stretch')
st.caption(f'Aperçu limité à 300 lignes. Le téléchargement contient toutes les {report["output_rows"]} lignes, toutes les colonnes. 1 ligne d’en-tête ; UTF-8 ; séparateur point-virgule.')
st.download_button('Télécharger le FEC enrichi — un seul CSV',content,'FEC_ENRICHI_ANALYTIQUE.csv','text/csv',type='primary')
st.caption('Le lettrage est conservé dans le fichier. Sa reprise effective dans Pennylane dépend du parcours et du mapping choisis. Le fichier enrichi n’est pas un FEC réglementaire : conserver le FEC initial.')
