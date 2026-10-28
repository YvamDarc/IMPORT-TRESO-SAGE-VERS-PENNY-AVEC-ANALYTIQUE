import hashlib,json
from collections import Counter
import streamlit as st
import pandas as pd
from fusion import reconcile,make_export,ConversionError,HELP,csv_bytes
st.set_page_config(page_title='FEC + analytique Sage',page_icon='🔗',layout='wide')
st.title('FEC + analytique Sage → Pennylane')
st.write('Dates et références de facture du FEC · numéro interne et analytique du PNM')
st.info('Date comptable = EcritureDate du FEC, ligne par ligne. Aucune modification de date, aucun regroupement en fin de mois.')
with st.sidebar:
    ff=st.file_uploader('1. FEC de référence',type=['txt','csv','fec'])
    pp=st.file_uploader('2. Export analytique Sage',type=['pnm','txt'])
    enc=st.selectbox('Encodage PNM',['cp850','cp1252','utf-8-sig'])
    st.caption('En-tête : 1 ligne pour chaque fichier. Les simulations PNM sont exclues.')
    manual_file=st.file_uploader('Rapprochements manuels sauvegardés',type=['json'])
    family=st.text_input('Famille analytique du plan 1','Plan 1')
    st.caption('Traitement en mémoire sur le serveur Streamlit. Aucun envoi ni suppression dans Pennylane.')
if not ff or not pp:st.stop()
fr=ff.getvalue();pr=pp.getvalue();digest=hashlib.sha256(fr+pr+enc.encode()).hexdigest()
manual={}
if manual_file:
    try:
        saved=json.loads(manual_file.getvalue())
        if saved['source']!=digest:raise ValueError('Le paramétrage concerne d’autres fichiers.')
        manual=saved['links']
    except (ValueError,KeyError,TypeError) as e:st.error(str(e));st.stop()
if st.session_state.get('source')!=digest:
    st.session_state['source']=digest;st.session_state['manual']={};st.session_state.pop('reconciled',None)
manual.update(st.session_state['manual'])
key=(digest,json.dumps(manual,sort_keys=True))
try:
    if st.session_state.get('match_key')!=key:
        with st.spinner('Rapprochement des pièces et des lignes…'):
            st.session_state['reconciled']=reconcile(fr,pr,enc,manual)
        st.session_state['match_key']=key
    result=st.session_state['reconciled'];f,p,links,methods,unresolved=result
except (ConversionError,ValueError) as e:st.error(str(e));st.stop()
cols=st.columns(4)
cols[0].metric('Lignes FEC',len(f));cols[1].metric('Rapprochées',len(links));cols[2].metric('À rapprocher',len(unresolved));cols[3].metric('Dates modifiées','0')
with st.expander('Correspondance des journaux'):
    names={'10':'ODG','50':'BNP','51':'CMB','60':'ACH','70':'VTE','JRRAN':'JRRAN','OD':'OD'}
    js=sorted({r['JournalCode'] for r in f})
    edit=st.data_editor(pd.DataFrame([{'Journal FEC':j,'Journal Pennylane':names.get(j,j)} for j in js]),disabled=['Journal FEC'],hide_index=True,key='journals-'+digest)
    journals={r['Journal FEC']:r['Journal Pennylane'] for r in edit.to_dict('records')}
if unresolved:
    st.warning(f'{len(unresolved)} lignes ont plusieurs correspondances possibles. Les références internes restent vides plutôt que d’être inventées ; les charges/produits concernés sont signalés en analytique « À RAPPROCHER — REPRISE ».')
    with st.expander('Résoudre un rapprochement ambigu'):
        st.dataframe(pd.DataFrame(unresolved),hide_index=True,height=250)
        fi=st.selectbox('Ligne FEC à rapprocher',[r['Ligne FEC'] for r in unresolved])
        issue=next(r for r in unresolved if r['Ligne FEC']==fi)
        candidates=[int(x) for x in issue['Candidats PNM'].split(', ') if x]
        pm={r.line:r for r in p.records}
        st.dataframe(pd.DataFrame([{'Ligne PNM':i,'N° interne':pm[i].ref,'Libellé':pm[i].label,'Analytique':'; '.join(a.sub+' : '+str(a.signed) for a in pm[i].allocations)} for i in candidates]),hide_index=True)
        pi=st.selectbox('Ligne PNM correspondante',candidates,index=None,placeholder='Choisir après vérification')
        if st.button('Appliquer ce rapprochement',disabled=pi is None):
            st.session_state['manual'][str(fi)]=pi;st.rerun()
        st.download_button('Sauvegarder les rapprochements',json.dumps({'source':digest,'links':manual},ensure_ascii=False).encode(),'rapprochements.json')
pending=st.checkbox('Inclure les lignes non rapprochées avec signalement',value=True)
try:
    export_key=(key,json.dumps(journals,sort_keys=True),family,pending)
    if st.session_state.get('export_key')!=export_key:
        st.session_state['export']=make_export(result,journals,family,pending)
        st.session_state['export_key']=export_key
    rows,report,package=st.session_state['export']
except (ConversionError,ValueError) as e:st.error(str(e));st.stop()
st.subheader('Aperçu — dates réelles du FEC')
# Date filters apply only to preview, never silently to the exported scope.
months=sorted({r['_date'].strftime('%Y-%m') for r in f})
month=st.selectbox('Mois à visualiser',['Tous']+months)
search=st.text_input('Rechercher une facture, un fournisseur, un compte ou une référence interne')
view=rows
if month!='Tous':view=[r for r in view if r['Date'][6:]+'-'+r['Date'][3:5]==month]
if search:view=[r for r in view if search.casefold() in ' '.join(str(v) for v in r.values()).casefold()]
columns=['Date','Code journal','Numéro interne Sage','Identifiant écriture FEC','Référence facture FEC','Numéro de compte','Libellé','Débit','Crédit','Famille de catégories','Catégorie','Poids de la catégorie','Statut rapprochement']
st.dataframe(pd.DataFrame(view[:500],columns=columns),hide_index=True,width='stretch')
st.caption(f'Aperçu limité à 500 lignes ; le téléchargement comprend toutes les {len(f)} lignes comptables du FEC. 1 ligne d’en-tête.')
with st.expander('Contrôle des dates par mois',expanded=True):
    counts=Counter(r['_date'].strftime('%Y-%m') for r in f)
    st.dataframe(pd.DataFrame([{'Mois':m,'Lignes FEC':counts[m],'Dates modifiées':0} for m in sorted(counts)]),hide_index=True)
with st.expander('Pièces et ventilations à vérifier'):
    st.write(f"{report['ecritures_fec_desequilibrees']} écritures FEC déséquilibrées ; {report['ecritures_fec_multidates']} écritures FEC à plusieurs dates. Elles sont conservées sans modification. Le contrôle d’import Pennylane peut demander leur correction.")
    st.dataframe(pd.DataFrame(report['regles_analytiques']),hide_index=True)
st.success(f"Débit : {report['debit']} € · Crédit : {report['credit']} € · aucune date modifiée.")
st.caption('La référence fournisseur est proposée comme Numéro de pièce. Le numéro interne et l’identifiant FEC restent dans des colonnes distinctes de contrôle ; leur stockage dans Pennylane dépend des champs de votre écran d’import.')
st.download_button('Télécharger la fusion et les contrôles',package,'FEC_avec_analytique_dates_preservees.zip','application/zip',type='primary')
with st.expander('Import dans Pennylane'):
    st.text(HELP)
