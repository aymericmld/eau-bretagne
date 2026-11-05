# Construire le rapport dans Power BI Service

Ce guide assemble le tableau de bord dans le navigateur, sans Power BI Desktop. Le rapport lui-même reste à construire : ce dépôt fournit les données, les mesures et le plan des pages.

**À savoir :** les mesures DAX de `mesures.dax` n'ont pas pu être exécutées dans Power BI depuis cet environnement. Utilisez la section « Valeurs de contrôle » pour les valider.

## 1. Charger les données

1. Utilisez `donnees/eau_bretagne_modele.xlsx`, qui contient une feuille par table. Préférez-le aux CSV : leurs décimales avec un point peuvent être mal lues avec des paramètres régionaux français.
2. Dans votre espace de travail, créez un modèle sémantique depuis **Créer > Obtenir des données**, puis choisissez Excel. Selon votre compte, le fichier devra peut-être d'abord être déposé sur OneDrive.
3. Vérifiez que les colonnes `code_commune`, `code_departement` et `code_epci` sont de type **texte**.

Si l'import Excel ne propose pas toutes les feuilles, passez par la création d'un modèle avec Power Query en ligne et importez chaque CSV de `donnees/`, en indiquant UTF-8 et le point comme séparateur décimal.

## 2. Créer les relations

Ouvrez le modèle en édition web, puis créez ces relations, toutes en un-à-plusieurs et à filtrage simple.

| Côté « un » | Côté « plusieurs » |
|---|---|
| `dim_departement[code_departement]` | `dim_commune[code_departement]` |
| `dim_departement[code_departement]` | `fact_secteur[code_departement]` |
| `dim_departement[code_departement]` | `fact_nappes_mois[code_departement]` |
| `dim_commune[code_commune]` | `fact_prelevements[code_commune]` |
| `dim_commune[code_commune]` | `fact_restrictions_mois[code_commune]` |
| `dim_annee[annee]` | `dim_mois[annee]` |
| `dim_annee[annee]` | `fact_prelevements[annee]` |
| `dim_annee[annee]` | `fact_secteur[annee]` |
| `dim_annee[annee]` | `fact_taille[annee]` |
| `dim_mois[mois]` | `fact_restrictions_mois[mois]` |
| `dim_mois[mois]` | `fact_nappes_mois[mois]` |

Ajoutez ensuite les mesures de `mesures.dax` dans le modèle, puis appliquez le thème `theme_eau_bretagne.json` si votre édition le permet.

## 3. Construire les quatre pages

Le titre de chaque visuel doit énoncer le constat, pas seulement décrire le graphique.

### Page 1 : Vue régionale
Message : *L'eau potable domine, et trois quarts de l'eau vient de la surface.*
- Cartes : `Volume prélevé (Mm³)`, `Part des eaux de surface`, `Part des activités économiques`.
- Courbes : volume par `annee` et `usage`, une petite courbe par usage car les échelles diffèrent.
- Barres : `Volume sectoriel (Mm³)` par `secteur`, triées.
- Segment : `annee`.

### Page 2 : Territoires
Message : *L'exposition est plus forte dans l'est de la région.*
- Carte : `latitude`, `longitude`, couleur `classe_exposition`, info-bulle `nom_commune` et `indice_exposition`.
- Barres : `Indice moyen (pondéré par la population)` par `nom_epci`, 10 premiers.
- Carte : `Part des habitants en exposition très élevée`.
- Segment : `departement`.

Si les visuels cartographiques sont désactivés sur votre compte, remplacez la carte par un nuage de points `longitude` / `latitude`.

### Page 3 : Sécheresse
Message : *2017 a duré le plus longtemps, mais la crise a surtout frappé en 2022 et 2026.*
- Barres empilées par `annee` : `jours_alerte`, `jours_alerte_renforcee`, `jours_crise`, divisés par commune.
- Courbe : `Niveau des nappes (centile)` par `mois`.
- Carte : `Communes touchées par la crise`.
- Segments : `annee`, `departement`.

Indiquez sur la page que 2026 s'arrête au 15 septembre.

### Page 4 : Fiche commune
Message : *Quel est le risque de ma commune ?*
- Segment avec recherche : `nom_commune`.
- Titre dynamique : `Titre de la fiche`.
- Cartes : `indice_exposition`, `score_gravite_annuel`, `part_eau_surface`.
- Barres : `Jours de restriction par commune` par `annee`.
- Tableau : volume prélevé par `usage` et `milieu`.
- Encadré : « Indice relatif à la Bretagne. Il ne mesure pas votre consommation et ne remplace pas les arrêtés officiels. »

## 4. Valeurs de contrôle

Sans filtre autre que celui indiqué, le rapport doit afficher ces valeurs.

| Mesure | Filtre | Valeur attendue |
|---|---|---|
| `Volume prélevé (Mm³)` | 2024 | 276,4 |
| `Part des eaux de surface` | 2024 | 73,3 % |
| `Jours de restriction par commune` | 2022 | 131,5 |
| `Jours de crise par commune` | 2022 | 72,2 |
| `Communes touchées par la crise` | 2022 | 1 202 |
| `Habitants en exposition très élevée` | aucun | 1 159 452 |
| `Part des habitants en exposition très élevée` | aucun | 33,6 % |
| `Indice moyen (pondéré par la population)` | aucun | 53,7 |

## 5. Publier dans le portfolio

**Publier sur le web** rend le rapport public sans connexion, ce qui convient à ces données ouvertes et agrégées. Pour l'utiliser sans abonnement :

- Travaillez dans **Mon espace de travail** : les autres espaces de travail exigent une licence Pro ou Premium par utilisateur.
- Créez les mesures dans le **modèle sémantique**, pas au niveau du rapport : Microsoft n'accepte pas les mesures DAX de rapport dans cette publication.
- Vérifiez que le paramètre de locataire **Publish to web** est activé. Il faut pour cela un administrateur Power BI sur votre organisation.
- Ajoutez une image d'attente, qui reste visible en cas de forte affluence.

La publication s'effectue depuis **Fichier > Incorporer le rapport > Publier sur le web (public)**. Si elle n'est pas disponible, intégrez au portfolio des captures d'écran ou une courte vidéo du rapport.

Mentionnez les sources sur le rapport : Hub'Eau, VigiEau, Sirene et geo.api.gouv.fr.
