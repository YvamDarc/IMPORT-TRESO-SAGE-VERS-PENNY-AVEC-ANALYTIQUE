# FEC complet enrichi — aucune colonne d’origine modifiée

Cette version remplace le convertisseur précédent. Elle conserve le FEC et lui ajoute les informations du PNM. Elle ne renomme pas les journaux, ne modifie pas les dates, ne remplace pas les références et ne corrige pas les montants.

## Déploiement Streamlit

Mettre à jour les quatre fichiers à la racine du dépôt : `app.py`, `fusion.py`, `pnm.py`, `requirements.txt`. Fichier principal : `app.py`.

En local : double-cliquer sur `lancer_windows.bat` (Python installé), ou exécuter :

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address=localhost
```

## Utilisation

Charger le FEC initial et le fichier PNM analytique. Pour le fichier LAUNAY fourni, choisir CP850. Cliquer sur **Télécharger le FEC enrichi — un seul CSV**. Il n’y a pas de ZIP de données ni de fichiers de contrôle séparés : les informations utiles sont dans ce CSV.

Le mode par défaut conserve exactement une ligne par ligne du FEC, dans le même ordre. Le CSV téléchargé utilise UTF-8 avec BOM, un séparateur point-virgule et **1 ligne d’en-tête**. Le format physique du fichier peut donc différer du FEC tabulé d’origine, mais les valeurs de ses cellules et l’ordre de ses colonnes sont conservés, y compris espaces et zéros initiaux.

## Tout le FEC est conservé

Les colonnes d’origine restent à gauche, avec leurs noms et leurs valeurs exactes : JournalCode, JournalLib, EcritureNum, EcritureDate, CompteNum, CompteLib, CompAuxNum, CompAuxLib, PieceRef, PieceDate, EcritureLib, Debit, Credit, EcritureLet, DateLet, ValidDate, Montantdevise, Idevise. Les éventuelles colonnes supplémentaires du fichier initial sont aussi conservées.

Exemples : journal `60` reste `60`, `ACHATS` reste `ACHATS`, `50` reste `50`, `BNP PARIBAS` reste `BNP PARIBAS`. Aucune conversion automatique des codes numériques en codes alphabétiques.

La date comptable reste EcritureDate telle quelle, au format source AAAAMMJJ. PieceDate reste distincte. Le lettrage et sa date restent dans EcritureLet et DateLet, sans correction ni déduction.

## Colonnes ajoutées

- `NumeroPieceComptablePNM` : référence comptable interne issue du PNM.
- `FamilleAnalytique` : nom choisi pour le plan 1 ; autres plans distingués.
- `CategorieAnalytique` : section analytique du PNM.
- `PoidsAnalytique` : montant analytique rapporté au montant comptable, sans normalisation.
- `MontantAnalytiquePNM` : montant analytique signé.
- `IdentifiantLigneSource` : identifiant stable de la ligne du FEC.
- `StatutRapprochement` : ligne rapprochée, écart analytique source ou ligne à rapprocher.
- `DetailAnalytiquePNM` : détail JSON complet des ventilations rattachées, avant toute agrégation par section.
- `CandidatsPNM` : références internes et ventilations possibles en cas d’ambiguïté, au format JSON.

Vous pouvez choisir les colonnes utiles ensuite, dans Excel ou lors du mapping. Les colonnes de détail restent disponibles dans le même fichier.

## Plusieurs sections sur la même ligne

Par défaut, les catégories sont séparées par ` | ` dans une seule cellule ; famille, montant et poids suivent le même ordre. Une telle cellule n’est pas une catégorie unique à mapper directement dans Pennylane.

Le second mode, **Une ligne par catégorie analytique**, répète la ligne FEC pour chaque catégorie. Aucune cellule d’origine n’est changée, mais le nombre de lignes augmente. Pour un import acceptant ces répétitions, mapper `IdentifiantLigneSource` vers l’identifiant de ligne et les poids vers le champ correspondant ; ne pas additionner les débits/crédits répétés sans dédupliquer l’identifiant.

## Incertitudes conservées, pas masquées

Le rapprochement ne choisit pas au hasard entre plusieurs factures identiques. Dans ces cas, numéro interne et catégorie restent vides, le statut indique À RAPPROCHER et CandidatsPNM conserve les possibilités. Aucune ligne comptable n’est supprimée. Aucune catégorie fictive « attente » n’est ajoutée.

Les écarts entre ventilation et montant comptable ne sont plus corrigés automatiquement : le détail source est conservé et le statut les signale. Un poids source supérieur à 100 % ou une somme de poids incohérente peut demander une correction avant un import multi-catégories ; le FEC lui-même reste intact.

## Contrôles sur le dossier fourni

- 37 778 lignes source et 37 778 lignes exportées dans le mode par défaut.
- 18 colonnes d’origine ; comparaison de toutes les cellules : aucune modification.
- JournalCode et JournalLib strictement conservés.
- 19 960 lignes avec un EcritureLet renseigné conservées, ainsi que toutes les valeurs de DateLet.
- 35 860 rapprochements automatiques ; 1 918 lignes ambiguës signalées.
- 55 lignes rapprochées portent plusieurs catégories ; 13 écarts analytiques source signalés.
- Tests unitaires et interface Streamlit vérifiés, téléchargement unique et cache de session fonctionnels.

Le fichier enrichi conserve les données du FEC mais n’est pas un FEC réglementaire, puisqu’il comporte des colonnes supplémentaires. La conservation du lettrage dans le CSV ne garantit pas sa reprise par tous les parcours d’import Pennylane. Aucun import ni remplacement du dossier n’a été effectué. Conserver le FEC initial et choisir le parcours/mapping adapté avant de remplacer l’ancien import.
