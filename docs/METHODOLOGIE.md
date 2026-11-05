# Méthodologie détaillée

Ce document explique chaque choix du projet : les données retenues, leurs défauts, les traitements appliqués et ce que les résultats permettent, ou non, de conclure. Pour une vue d'ensemble, commencez par le [README](../README.md).

## 1. Cadrage

Le projet est parti d'une question simple : quelles données ouvertes peuvent servir à une PME bretonne tout en portant un enjeu environnemental ?

L'exploration a fait évoluer le sujet. Au départ, l'idée était de mesurer l'eau consommée par les PME. Or Hub'Eau ne recense que les prélèvements directs dans le milieu. L'eau achetée au réseau public, celle de la plupart des PME, y figure en « eau potable », sans distinction d'utilisateur. Des sources régionales citent 34 à 45 millions de m³ pour le seul agroalimentaire, contre 21 millions ici pour toutes les activités économiques. Une grande partie de l'eau des entreprises est donc probablement absente, sans que ces données permettent de le confirmer.

La question a été reformulée en conséquence : **quels territoires sont les plus exposés ?** Une restriction s'applique à tous les usagers d'une commune, y compris aux entreprises raccordées au réseau. L'exposition du territoire est donc pertinente pour une PME, même si sa consommation reste inconnue.

## 2. Les données

| Source | Contenu | Période | Maille |
|---|---|---|---|
| Hub'Eau Prélèvements | Volumes annuels déclarés, usage, type de milieu | 2008-2024 | Ouvrage |
| VigiEau Historique Communes | Niveau de restriction quotidien par type de ressource | 2012 au 15 sept. 2026 pour les jours de restriction | Commune |
| Hub'Eau Piézométrie | Niveau quotidien des nappes, 57 stations | Depuis 2008 | Station |
| API Recherche d'entreprises | Code NAF et catégorie d'entreprise | Situation actuelle | Entreprise |
| API Découpage administratif | Communes, EPCI, population, surface | Situation actuelle | Commune |

Les données ont été collectées le 5 novembre 2026.

### Lecture en flux de VigiEau

L'historique communal est un fichier national : 586 Mo compressés, 11,9 Go décompressés. Les communes bretonnes n'en représentent qu'une petite partie. Le pipeline lit donc l'archive pendant son téléchargement, découpe le JSON commune par commune et ne conserve que les jours avec une restriction en Bretagne. Il s'arrête dès que le fichier, trié par code INSEE, dépasse le Morbihan. Rien de volumineux n'est écrit sur le disque. Un test unitaire vérifie ce découpage avec des coupures arbitraires dans le flux.

## 3. Nettoyage

| Problème constaté | Traitement | Raison |
|---|---|---|
| Eau turbinée de 1 à 2,7 milliards de m³ par an | Exclue, comme les canaux | Elle retourne au cours d'eau et écraserait tous les autres usages |
| Doublons par ouvrage, année et usage | Le volume le plus élevé est conservé | Une seule ligne par clé est nécessaire ; ce choix reste une convention |
| Volumes nuls | Conservés dans les totaux, exclus des comptages d'ouvrages actifs | Un volume nul signifie qu'il n'y a pas eu d'usage déclaré |
| Communes fusionnées (4 codes Hub'Eau) | Table de passage explicite | Certains ouvrages n'ont pas de coordonnées |
| 4 communes VigiEau hors référentiel | Écartées | Leurs communes de rattachement ont leur propre historique |
| Communes homonymes entre départements | Recherche par département et nom | Le nom seul n'est pas unique |

## 4. Rapprochement avec Sirene

Hub'Eau ne donne ni secteur ni taille, seulement un nom libre comme « USINE DE… ». Chaque nom est nettoyé puis recherché dans l'API Recherche d'entreprises.

Un premier essai fondé sur la similarité des noms a produit de faux positifs. Deux garde-fous ont été ajoutés :

1. **Un mot distinctif commun** : les mots génériques comme « golf » ou « usine » ne comptent pas.
2. **Un établissement dans la même commune** : un nom courant sans ancrage local donne trop d'homonymes.

Résultat : 183 ouvrages sur 255 sont rapprochés, soit 90 % du volume de la dernière année connue de chaque ouvrage. Les ouvrages restants gardent une taille « Non classé ».

Le code NAF ne suffit pas toujours, car celui d'une entité mère peut être commercial ou immobilier. Le fichier [`corrections_secteur.csv`](../data/reference/corrections_secteur.csv) complète donc le classement, sur mots entiers. Une partie de ces corrections repose sur le nom de l'ouvrage et sur une connaissance générale des groupes concernés. Elle n'a pas été vérifiée site par site. Au total, 32 ouvrages restent en secteur « Non identifié ».

**La taille d'entreprise** utilise la catégorie Insee. Une filiale de grand groupe y apparaît comme grande entreprise, même si le site est modeste.

## 5. Indicateurs

### Jours de restriction

Pour chaque commune et chaque jour, le niveau retenu est le plus sévère parmi les ressources concernées : eau potable, eaux souterraines et eaux de surface. Les jours de restriction comptent l'alerte, l'alerte renforcée et la crise. La vigilance est comptée à part, car elle n'impose pas de restriction en elle-même.

### Score de gravité

Compter les jours placerait 2017 très en tête, alors que cette année n'a connu aucun jour de crise. Le score pondère donc les jours : alerte 1, alerte renforcée 2, crise 3. Cette échelle est conventionnelle.

### Niveau des nappes

Une nappe est naturellement plus basse en automne qu'au printemps. Chaque mois est donc comparé aux mêmes mois de la même station, sous forme de centile, à condition de disposer d'au moins 8 années. La valeur départementale est la médiane des stations.

### Périmètre constant

Comparer des totaux annuels mélange l'évolution réelle et l'entrée de nouveaux ouvrages dans la base. Pour 2021-2023, l'analyse se limite aux 130 ouvrages actifs les trois années.

## 6. Indice d'exposition

L'indice classe les 1 202 communes les unes par rapport aux autres :

```text
indice = 0,5 × rang(gravité) + 0,3 × rang(pression) + 0,2 × rang(eaux de surface)
```

- **Gravité :** score moyen annuel sur 2016-2025, par commune. L'année 2026, incomplète, est exclue.
- **Pression :** m³ prélevés par km² sur 2020-2024, par EPCI, pour éviter qu'une commune sans ouvrage paraisse sans pression.
- **Eaux de surface :** part du volume prélevé en surface sur 2020-2024, par EPCI.

Les rangs centiles évitent qu'une valeur extrême domine. Les quatre classes ont le même effectif : ce sont des positions relatives, pas des seuils de danger.

### Test de sensibilité

| Scénario | Corrélation de rang | Quartile haut conservé |
|---|---|---|
| Poids égaux | 0,89 | 77 % |
| Gravité dominante (70/20/10) | 0,89 | 70 % |
| Pression dominante (30/50/20) | 0,86 | 80 % |
| Eaux de surface renforcées (40/20/40) | 0,93 | 81 % |

L'ordre général résiste, mais 19 à 30 % des communes du quartile le plus exposé changent. L'indice convient pour repérer de grandes zones, pas pour comparer deux communes voisines.

## 7. Vérifications

Plusieurs résultats ont été contrôlés parce qu'ils semblaient anormaux.

**2017 était-elle un artefact ?** Avec 207 jours par commune, cette année dépassait 2022. Les arrêtés s'enchaînent pourtant de février à octobre, et un document préfectoral indépendant cite l'état d'alerte du Morbihan au 3 février 2017. Le chiffre est conservé.

**Pourquoi le total monte-t-il en 2022 ?** Une première hypothèse de changement de code a été testée et n'a pas été confirmée. Cinq ouvrages aux codes consécutifs entrent dans la base pour 1,8 million de m³, sans prédécesseur identifiable, et presque rien ne s'arrête en 2021. Cela ressemble à un enregistrement groupé de sites existants. Cette explication reste à confirmer.

**Pourquoi Rennes Métropole affiche-t-elle 5 % d'eau de surface ?** L'indicateur mesure le lieu de prélèvement, pas l'origine de l'eau consommée. Une grande ville peut être alimentée par des ressources situées hors de son territoire. Cette limite s'applique à tout l'indice.

### Contrôles automatiques

Le pipeline refuse de publier si l'un de ces contrôles échoue : clés uniques, communes présentes dans le référentiel, mois présents dans le calendrier, volumes réconciliés avec la source, nombre de jours compatible avec le mois, indice complet et compris entre 0 et 100, absence de colonne nominative.

## 8. Confidentialité

Les noms d'ouvrages sont publics dans Hub'Eau, mais un classement public d'entreprises locales n'apporterait rien à l'analyse. Les règles suivantes s'appliquent :

- aucun volume n'est publié avec un nom d'entreprise ;
- les résultats par secteur sont agrégés par département et masqués sous 3 ouvrages ;
- la table des ouvrages nommés reste locale et hors du dépôt.

Les volumes par commune restent publiés, comme dans la source. Dans une petite commune, ils peuvent correspondre à un seul ouvrage. Le fichier de corrections cite des noms de groupes, car le pipeline en a besoin, mais il ne contient aucun volume.

## 9. Limites

- La consommation réelle des entreprises raccordées au réseau n'est pas mesurée.
- Le lieu de prélèvement ne reflète pas toujours le lieu d'usage.
- 78 % des écarts de gravité s'expliquent par le département : les arrêtés dépendent aussi de pratiques préfectorales.
- Sur 2016-2025, toutes les communes des Côtes-d'Armor et du Finistère ont le même nombre de jours de restriction. Dans ces départements, l'écart d'indice entre communes vient donc surtout des composantes calculées par EPCI et des niveaux de gravité.
- La pression et la part d'eau de surface sont corrélées (0,69), ce qui compte en partie deux fois le même phénomène.
- Les volumes annuels ne montrent pas l'effet d'un été sec.
- Les prélèvements sont des déclarations, dont une partie est forfaitaire ou estimée.
- La baisse de long terme peut venir de la sobriété, de fermetures ou d'un passage au réseau public.
- Le lien entre la crise de 2022 et la baisse à périmètre constant n'est pas démontré.
- Une corrélation entre nappes et restrictions ne décrit pas le processus de décision.
- Les EPCI à cheval sur deux régions ne sont pris en compte que pour leur partie bretonne.
- Seules les publications officielles des préfectures font foi pour les restrictions.

## 10. Pistes d'amélioration

- Relier les communes à leur service d'eau potable pour remplacer le lieu de prélèvement par l'origine réelle de l'eau.
- Confirmer avec l'agence de l'eau l'origine des ouvrages apparus en 2022.
- Vérifier les corrections de secteur avec des acteurs locaux.
- Ajouter une projection climatique pour passer du constat à l'anticipation.
