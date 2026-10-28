# Fusion FEC + analytique Sage — dates conservées

Cette version remplace l’ancienne application PNM seul. Elle prend deux fichiers : le FEC initial et le PNM avec analytique. Elle ne charge pas les anciens profils qui modifiaient certaines dates.

## Déployer

Dans votre dépôt Streamlit, remplacer `app.py` et `requirements.txt`, puis ajouter `fusion.py` et `pnm.py`, tous à la racine. Le fichier principal reste `app.py`. Aucun fichier comptable client n’est inclus dans ce paquet.

Pour un lancement local Windows, extraire le ZIP et ouvrir `lancer_windows.bat` (Python requis). Ou :

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address=localhost
```

## Utilisation

1. Charger le FEC de référence et le PNM analytique dans la barre latérale.
2. Laisser CP850 pour le PNM LAUNAY fourni. Chaque source a 1 ligne d’en-tête.
3. Vérifier l’aperçu ; sélectionner un mois pour voir ses dates réelles. Les filtres concernent l’aperçu seulement, pas le périmètre exporté.
4. Télécharger le ZIP de fusion et de contrôle.

## Les dates : règle impérative

**Date = EcritureDate de chaque ligne du FEC.** La date n’est jamais remplacée par le 1er janvier, une date de facture devinée, une date de fin de mois ou celle d’une autre ligne. `PieceDate`, conservée séparément, n’est pas utilisée pour dater la comptabilisation. Une date du FEC invalide est signalée, pas remplacée.

Les cinq pièces de l’aperçu précédent étaient réellement comptabilisées au 01/01/2026. Cela ne constitue pas une règle appliquée aux autres pièces. Le nouveau contrôle vérifie la date de chaque ligne exportée par rapport au FEC, et la table par mois montre le périmètre réel.

Les pièces déséquilibrées et les écritures FEC comprenant plusieurs dates restent inchangées. Les traitements de l’ancienne version qui modifiaient sept dates ont été supprimés de ce parcours.

## Deux références distinctes

| Colonne | Origine |
|---|---|
| Date | EcritureDate du FEC, format JJ/MM/AAAA |
| Date pièce FEC | PieceDate du FEC, conservée comme contrôle |
| Numéro de pièce | PieceRef du FEC ; EcritureNum seulement si PieceRef est vide |
| Référence facture FEC | PieceRef original, y compris s’il est vide |
| Numéro interne Sage | Référence interne de la ligne PNM rapprochée |
| Identifiant écriture FEC | EcritureNum du FEC |
| Libellé | EcritureLib du FEC |
| Débit / Crédit | Montants du FEC |
| Famille / Catégorie / Poids | Ventilation PNM rattachée à la ligne FEC |

Le numéro interne et l’identifiant d’écriture restent dans des colonnes distinctes de contrôle du CSV. Leur conservation dans un champ de Pennylane dépend des champs disponibles dans votre écran de mapping ; le convertisseur ne prétend pas qu’un second numéro de pièce sera automatiquement créé dans Pennylane.

## Rapprochement

Les deux fichiers doivent contenir les mêmes lignes comptables, simulations PNM exclues. La comparaison porte sur journal, date, compte, auxiliaire, montant signé et nombre d’occurrences.

Les correspondances sont établies par clé comptable complète, libellé, signature de pièce et autres lignes déjà rapprochées de la même pièce. Jamais par le montant seul ni par l’ordre arbitraire des lignes. Lorsque plusieurs factures identiques ont des sections différentes, aucun choix automatique n’est effectué.

Les lignes ambiguës sont présentées avec les candidats PNM, leurs références internes et leurs ventilations. Un rapprochement manuel peut être choisi et sauvegardé ; il est lié à l’empreinte des deux fichiers.

L’export avec signalement est activé par défaut : aucune ligne du FEC n’est omise, mais le numéro interne reste vide pour les lignes non rapprochées. Les charges/produits non rapprochés sont affectés à `À RAPPROCHER — REPRISE`, et leur analytique source reste dans le fichier de contrôle. Désactiver cette option empêche l’export tant que tous les rapprochements ne sont pas résolus.

## Écarts analytiques

- Une section unique est ramenée au montant de la ligne comptable.
- Une sous-ventilation multi-sections conserve les affectations connues et place le reliquat en `À VÉRIFIER — REPRISE`.
- Une surventilation multi-sections incohérente est isolée dans cette catégorie, sans inventer de répartition.
- Les régularisations d’une même section sont agrégées ; les montants comptables restent inchangés.
- Les traitements sont listés dans le ZIP avec toutes les ventilations PNM originales.

## Vérification sur les fichiers fournis

37 778 lignes FEC, 35 860 rapprochements automatiques et 1 918 lignes restant à rapprocher. Parmi ces dernières, 214 lignes ont des candidats PNM portant de l’analytique : une affectation sans contrôle serait incertaine. Le reste concerne notamment des références internes indistinguables, sur des lignes sans analytique.

Chaque date exportée a été comparée à celle de sa ligne FEC : **0 date modifiée**. Débit et crédit du FEC : 44 421 870,28 € chacun. Contrôles unitaires, test Streamlit avec les deux fichiers et filtre de juin exécutés. Aucun import réel dans Pennylane n’a été effectué.

Le FEC contient également 10 écritures déséquilibrées par EcritureNum et 99 écritures comprenant plusieurs dates. Les références de document peuvent être réutilisées ou différer entre lignes d’une écriture : le contrôle Pennylane peut demander un retraitement. L’application conserve les données et les dates ; elle ne garantit pas l’acceptation sans intervention de ces cas par Pennylane.

## Importer

Dans Saisie > Imports > Écritures, utiliser `01_FUSION_PENNYLANE.csv` : UTF-8, séparateur point-virgule, **1 ligne d’en-tête**.

Mapper Date, Code journal, Numéro de pièce, Numéro de compte, Libellé, Débit, Crédit, Identifiant de ligne, Famille de catégories, Catégorie et Poids de la catégorie. Ne pas mapper les autres colonnes vers des champs comptables différents de leur sens. Les montants sont répétés pour les différentes catégories d’une même ligne : l’Identifiant de ligne est indispensable.

Le nouveau CSV ne remplace pas automatiquement le FEC déjà importé. Organiser la suppression du seul import à remplacer avant réimport pour éviter les doublons. Ce parcours ne reprend pas automatiquement lettrage, pièces jointes ou transactions de gestion du parcours FEC.

Références :
- https://help.pennylane.com/fr/articles/18793-importer-des-ecritures
- https://help.pennylane.com/fr/articles/74963-importer-des-ecritures-comptables-avec-plusieurs-categories-analytiques

## Tests

`python -m unittest -v`
