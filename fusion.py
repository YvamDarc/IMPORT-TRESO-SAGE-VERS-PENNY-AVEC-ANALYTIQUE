import csv,io,json,hashlib,unicodedata
from collections import defaultdict,Counter
from decimal import Decimal as D
from datetime import datetime
from zipfile import ZipFile,ZIP_DEFLATED
from pnm import parse_pnm,amount,money,csv_bytes,ConversionError

def label(s):
    s=unicodedata.normalize('NFKD',s.replace('€','_')).upper()
    return ''.join(c for c in s if c.isalnum())[:20]

def read_fec(raw,encoding='auto'):
    encs=['utf-8-sig','cp1252'] if encoding=='auto' else [encoding]
    for enc in encs:
        try:txt=raw.decode(enc);break
        except UnicodeDecodeError:continue
    else:raise ConversionError('Encodage FEC non reconnu.')
    sep='\t' if '\t' in txt.splitlines()[0] else ';'
    reader=csv.DictReader(io.StringIO(txt),delimiter=sep)
    needed=['JournalCode','EcritureNum','EcritureDate','CompteNum','CompAuxNum','PieceRef','PieceDate','EcritureLib','Debit','Credit']
    if not set(needed)<=set(reader.fieldnames or []):raise ConversionError('Colonnes FEC obligatoires manquantes.')
    rows=[]
    for i,row in enumerate(reader,2):
        r={k:(v or '').strip() for k,v in row.items() if k}
        try:
            r['_date']=datetime.strptime(r['EcritureDate'],'%Y%m%d').date()
            r['_signed']=amount(r['Debit'])-amount(r['Credit'])
            if amount(r['Debit'])<0 or amount(r['Credit'])<0 or (amount(r['Debit']) and amount(r['Credit'])):raise ConversionError('Débit/crédit inhabituels.')
        except (ValueError,ConversionError) as e:raise ConversionError(f'FEC ligne {i} : {e}')
        r['_line']=i;rows.append(r)
    if not rows:raise ConversionError('FEC vide.')
    return rows

def coref(r):return(r['JournalCode'][:3],r['_date'],r['CompteNum'],r['CompAuxNum'],r['_signed'])
def corep(r):return(r.journal,r.date,r.account,r.sub if r.kind=='X' else '',r.signed)
def afingerprint(r):return tuple(sorted((a.plan,a.sub,a.signed) for a in r.allocations))

def reconcile(fraw,praw,pencoding='cp850',manual=None):
    f=read_fec(fraw);p=parse_pnm(praw,encoding=pencoding);manual=manual or {}
    if Counter(coref(r) for r in f)!=Counter(corep(r) for r in p.records):
        raise ConversionError('FEC et PNM ne contiennent pas les mêmes lignes comptables (dates, journaux, comptes, auxiliaires ou montants). Vérifiez la période et les simulations.')
    # Never infer a link from row order or from an amount alone.
    fmap={r['_line']:r for r in f};pmap={r.line:r for r in p.records};links={};used=set();methods={}
    def attach(fi,pi,method):links[fi]=pi;used.add(pi);methods[fi]=method
    for fi,pi in manual.items():
        fi=int(fi);pi=int(pi)
        if fi not in fmap or pi not in pmap or coref(fmap[fi])!=corep(pmap[pi]) or pi in used:raise ConversionError('Rapprochement manuel incompatible ou réutilisé.')
        attach(fi,pi,'Manuel')
    def buckets(extra=False):
        fb=defaultdict(list);pb=defaultdict(list)
        for r in f:
            if r['_line'] not in links:fb[coref(r)+(label(r['EcritureLib']),) if extra else coref(r)].append(r['_line'])
        for r in p.records:
            if r.line not in used:pb[corep(r)+(label(r.label),) if extra else corep(r)].append(r.line)
        return fb,pb
    for extra in [True,False]:
        fb,pb=buckets(extra)
        for k,ii in fb.items():
            jj=pb.get(k,[])
            if len(ii)==len(jj)==1:attach(ii[0],jj[0],'Clé complète + libellé' if extra else 'Clé comptable unique')
    # Match whole balanced/document groups by their complete multiset, not sequence.
    fg=defaultdict(list);pg=defaultdict(list)
    for r in f:fg[r['JournalCode'],r['EcritureNum']].append(r)
    for r in p.records:pg[r.piece].append(r)
    fs=defaultdict(list);ps=defaultdict(list)
    for k,rs in fg.items():fs[tuple(sorted(coref(r) for r in rs))].append(k)
    for k,rs in pg.items():ps[tuple(sorted(corep(r) for r in rs))].append(k)
    for sig,keys in fs.items():
        pkeys=ps.get(sig,[])
        if len(keys)!=1 or len(pkeys)!=1:continue
        fr=fg[keys[0]];pr=pg[pkeys[0]]
        # Reject a whole-piece inference conflicting with a proven individual match.
        ids={r.line for r in pr}
        if any(r['_line'] in links and links[r['_line']] not in ids for r in fr):continue
        for r in fr:
            fi=r['_line']
            if fi in links:continue
            cand=[x for x in pr if x.line not in used and corep(x)==coref(r)]
            tight=[x for x in cand if label(x.label)==label(r['EcritureLib'])]
            if tight:cand=tight
            if len(cand)==1 or (cand and len({afingerprint(x) for x in cand})==1):
                attach(fi,cand[0].line,'Signature complète de pièce unique')
    # A unique sibling-vote links a source piece to its FEC entry, only when reciprocal.
    for _ in range(3):
        votes=defaultdict(set);reverse=defaultdict(set)
        for fi,pi in links.items():
            fg=(fmap[fi]['JournalCode'],fmap[fi]['EcritureNum']);pg=pmap[pi].piece
            votes[fg].add(pg);reverse[pg].add(fg)
        changed=False;fb,pb=buckets()
        for k,ii in fb.items():
            for fi in ii:
                fg=(fmap[fi]['JournalCode'],fmap[fi]['EcritureNum'])
                if len(votes.get(fg,set()))!=1:continue
                pg=next(iter(votes[fg]))
                if len(reverse[pg])!=1:continue
                candidates=[pi for pi in pb.get(k,[]) if pi not in used and pmap[pi].piece==pg]
                if len(candidates)==1:attach(fi,candidates[0],'Pièce rapprochée par ses autres lignes');changed=True
        if not changed:break
    # Interchangeable duplicate rows are safe only if piece, label and analytic amounts agree.
    fb,pb=buckets()
    for k,ii in fb.items():
        jj=[pi for pi in pb.get(k,[]) if pi not in used]
        if len(ii)==len(jj) and jj and len({(pmap[pi].ref,label(pmap[pi].label),afingerprint(pmap[pi])) for pi in jj})==1:
            for fi,pi in zip(sorted(ii),sorted(jj)):attach(fi,pi,'Lignes équivalentes (même référence et analytique)')
    unresolved=[]
    fb,pb=buckets()
    for k,ii in fb.items():
        for fi in ii:unresolved.append({'Ligne FEC':fi,'Date':fmap[fi]['_date'].strftime('%d/%m/%Y'),'Écriture FEC':fmap[fi]['EcritureNum'],
            'Facture':fmap[fi]['PieceRef'],'Compte':fmap[fi]['CompteNum'],'Libellé':fmap[fi]['EcritureLib'],
            'Candidats PNM':', '.join(str(pi) for pi in pb.get(k,[]) if pi not in used)})
    return f,p,links,methods,unresolved

def make_export(result,journals=None,family='Plan 1',pending=True):
    f,p,links,methods,unresolved=result;pm={r.line:r for r in p.records}
    default={'10':'ODG','50':'BNP','51':'CMB','60':'ACH','70':'VTE','JRRAN':'JRRAN','OD':'OD'}
    journals=journals or {r['JournalCode']:default.get(r['JournalCode'],r['JournalCode']) for r in f}
    import re
    if any(not re.fullmatch('[A-Za-z]{1,5}',v) for v in journals.values()):raise ConversionError('Les journaux cibles doivent avoir 1 à 5 lettres.')
    if len(set(journals.values()))!=len(journals):raise ConversionError('Deux journaux source partagent un code cible.')
    if unresolved and not pending:raise ConversionError(f'{len(unresolved)} lignes à rapprocher. Activez l’export avec signalement ou complétez les rapprochements.')
    rows=[];audit=[];actions=[];grouped=defaultdict(D);dates=defaultdict(set)
    for r in f:
        fi=r['_line'];pr=pm.get(links.get(fi));account=r['CompAuxNum'] or r['CompteNum']
        if r['CompAuxNum'] and not account.startswith(r['CompteNum'][:3]):account=r['CompteNum'][:3]+account
        # The canonical date and document reference ALWAYS come directly from this FEC row.
        base={'Date':r['_date'].strftime('%d/%m/%Y'),'Code journal':journals[r['JournalCode']],
              'Numéro de pièce':r['PieceRef'] or r['EcritureNum'],'Numéro de compte':account,
              'Libellé':r['EcritureLib'],'Débit':money(amount(r['Debit'])),'Crédit':money(amount(r['Credit'])),
              'Identifiant de ligne':f'FEC-{fi:07d}','Famille de catégories':'','Catégorie':'','Poids de la catégorie':'',
              'Numéro interne Sage':pr.ref if pr else '', 'Identifiant écriture FEC':r['EcritureNum'],
              'Référence facture FEC':r['PieceRef'],'Date pièce FEC':r['PieceDate'],
              'Compte général FEC':r['CompteNum'],'Auxiliaire FEC':r['CompAuxNum'],
              'Statut rapprochement':methods.get(fi,'À RAPPROCHER')}
        grouped[r['JournalCode'],r['EcritureNum']]+=r['_signed'];dates[r['JournalCode'],r['EcritureNum']].add(r['_date'])
        audit.append({'Ligne FEC':fi,'Ligne PNM':pr.line if pr else '', 'Date FEC':r['EcritureDate'],
                      'Date export':r['_date'].strftime('%Y%m%d'),'Pièce FEC':r['PieceRef'],
                      'Pièce interne Sage':pr.ref if pr else '', 'Méthode':methods.get(fi,'À RAPPROCHER')})
        if not pr:
            if r['CompteNum'].startswith(('6','7')) and r['_signed']:
                rows.append(dict(base,**{'Famille de catégories':family,'Catégorie':'À RAPPROCHER — REPRISE','Poids de la catégorie':'1'}))
            else:rows.append(base)
            continue
        if not pr.allocations:rows.append(base);continue
        plans=defaultdict(list)
        for a in pr.allocations:plans[a.plan].append(a)
        for plan,alloc in plans.items():
            cats=defaultdict(D)
            for a in alloc:cats[a.sub]+=a.signed
            total=sum(cats.values());status='Conservé'
            if total!=r['_signed']:
                if len(cats)==1 and total*r['_signed']>0:
                    cats={next(iter(cats)):r['_signed']};status='Section unique ramenée à 100 %'
                elif total*r['_signed']>0 and abs(total)<abs(r['_signed']):
                    cats['À VÉRIFIER — REPRISE']+=r['_signed']-total;status='Reliquat isolé'
                else:cats={'À VÉRIFIER — REPRISE':r['_signed']};status='Répartition incohérente isolée'
            if not r['_signed'] or any(n*r['_signed']<0 for n in cats.values()):
                cats={'À VÉRIFIER — REPRISE':r['_signed']};status='Répartition de sens contraire isolée'
            if not r['_signed']:raise ConversionError(f'Analytique sur montant nul, ligne FEC {fi}.')
            active=[(c,n) for c,n in cats.items() if n]
            weights=[(n/r['_signed']).quantize(D('.000000000001')) for c,n in active]
            weights[-1]+=D(1)-sum(weights)
            for (cat,n),weight in zip(active,weights):
                rows.append(dict(base,**{'Famille de catégories':family if plan=='1' else f'Plan {plan}',
                                        'Catégorie':cat,'Poids de la catégorie':str(weight).replace('.',',')}))
            if status!='Conservé':actions.append({'Ligne FEC':fi,'Ligne PNM':pr.line,'Libellé':r['EcritureLib'],'Plan':plan,'Montant comptable':money(r['_signed']),'Total analytique source':money(total),'Traitement':status})
    unique={r['Identifiant de ligne']:r for r in rows}
    assert len(unique)==len(f)
    assert all(unique[f'FEC-{r["_line"]:07d}']['Date']==r['_date'].strftime('%d/%m/%Y') for r in f)
    assert all(unique[f'FEC-{r["_line"]:07d}']['Référence facture FEC']==r['PieceRef'] for r in f)
    report={'lignes_fec':len(f),'lignes_csv':len(rows),'lignes_rapprochees':len(links),'lignes_a_rapprocher':len(unresolved),
        'dates_modifiees':0,'reference_facture':'PieceRef du FEC','date_comptable':'EcritureDate du FEC',
        'debit':money(sum(amount(r['Debit']) for r in f)),'credit':money(sum(amount(r['Credit']) for r in f)),
        'ecritures_fec_desequilibrees':sum(v!=0 for v in grouped.values()),'ecritures_fec_multidates':sum(len(ds)>1 for ds in dates.values()),
        'regles_analytiques':actions,'sha256_pnm':p.digest}
    buf=io.BytesIO()
    with ZipFile(buf,'w',ZIP_DEFLATED) as z:
        z.writestr('01_FUSION_PENNYLANE.csv',csv_bytes(rows));z.writestr('02_RAPPROCHEMENT.csv',csv_bytes(audit))
        z.writestr('03_A_RAPPROCHER.csv',csv_bytes(unresolved));z.writestr('04_REGLES_ANALYTIQUES.csv',csv_bytes(actions))
        z.writestr('05_RAPPORT.json',json.dumps(report,ensure_ascii=False,indent=2))
        z.writestr('06_PNM_ANALYTIQUE_SOURCE.csv',csv_bytes([{'Ligne PNM':r.line,'Ligne ventilation':a.line,'Référence interne':r.ref,'Plan':a.plan,'Section':a.sub,'Montant signé':money(a.signed)} for r in p.records for a in r.allocations]))
        z.writestr('LIRE_AVANT_IMPORT.txt',HELP)
    return rows,report,buf.getvalue()

HELP='''Dates : EcritureDate du FEC, sans exception. Date pièce FEC est une autre colonne.
Numéro de pièce = PieceRef du FEC (référence fournisseur), sinon EcritureNum si vide.
Numéro interne Sage = référence du PNM, conservée séparément ; vide si non rapprochée.
Import : Saisie > Imports > Écritures ; UTF-8 ; séparateur ; ; 1 ligne d’en-tête.
Mapper Date, Code journal, Numéro de pièce, Numéro de compte, Libellé, Débit, Crédit,
Identifiant de ligne, Famille de catégories, Catégorie, Poids de la catégorie.
Les autres colonnes sont de contrôle : ne pas les associer à un champ comptable différent.
Le numéro interne et l’identifiant FEC sont conservés dans le fichier ; leur stockage dans
Pennylane dépend des champs disponibles dans votre écran d’import.
Les pièces déséquilibrées ou multidates restent telles que dans le FEC. Aucune date n’est
modifiée pour forcer une validation. Pennylane peut demander une correction de ces pièces.
Les rapprochements ambigus sont signalés ; aucune association n’est choisie au hasard.
Les ajustements analytiques sont tracés ; les ventilations source figurent dans le ZIP.
Le CSV est un import d’écritures, pas un FEC réglementaire. Aucun import n’a été exécuté.
Ne pas cumuler avec le FEC déjà importé : organiser son remplacement avant réimport.
Ce parcours ne reprend pas automatiquement le lettrage, les pièces jointes ou les transactions
de gestion issus du précédent parcours FEC. Conserver les fichiers sources.
'''
