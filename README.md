# Cartomax

Outil de cartographie interne pour l'analyse de sites logistiques et tertiaires en France.
L'application permet de placer des adresses sur une carte, de les confronter aux
infrastructures de transport, aux données cadastrales et aux zonages d'urbanisme, puis
d'exporter le résultat sous forme de visuel ou de tableau.

## Contenu du dépôt

| Élément | Rôle |
|---|---|
| `cartomax.html` | Application principale. Carte interactive plein écran avec barre latérale d'outils. |
| `carte_plu.html` | Application secondaire dédiée à l'analyse PLU (cadastre et zonage d'urbanisme). |
| `geojson/` | Jeux de données géographiques embarqués (réseaux, points d'intérêt, contours administratifs). |
| `style/` | Polices de la charte (Anton, Calibre). |

Il n'y a ni serveur, ni build, ni dépendance à installer : chaque page est un fichier
HTML autonome qui charge ses librairies depuis un CDN.

## Accès

Les deux pages sont protégées par un mot de passe simple, demandé au chargement.
La validation est mémorisée pour la durée de la session du navigateur : une seule
saisie suffit pour naviguer entre les deux pages, et le mot de passe est redemandé à la
prochaine ouverture du navigateur.

Il s'agit d'un verrou de confort, pas d'une sécurité réelle : le mot de passe est
présent dans le code source de la page et reste accessible à quelqu'un qui irait le
chercher. L'objectif est d'empêcher un accès accidentel, pas de protéger des données
sensibles.

## Fonctionnalités principales

### Application principale (`cartomax.html`)

**Saisie et gestion des points**
- Ajout d'adresses par géocodage ou par saisie de coordonnées.
- Organisation des points en groupes, avec styles et étiquettes personnalisables.
- Liste des points éditable, réordonnable et exportable.

**Couches de données**
- Réseau autoroutier, routes nationales, sorties et accès autoroutiers.
- Transports : TGV, TER, RER, métro, tramway, arrêts de bus, aéroports, ports.
- Infrastructures logistiques : stations GNL, bornes de recharge poids lourds, parkings.
- Services de proximité : restauration, alimentation, hôtellerie.
- Contours communaux et métropolitains, données INSEE.

**Analyses**
- Calculs de distance et de temps de trajet routier entre points.
- Distance aux points d'intérêt, aux accès autoroutiers et aux métropoles les plus proches.
- Isochrones (zones accessibles en un temps donné) et inventaire des données comprises
  dans l'isochrone.
- Consultation du cadastre et des zones PLU sur un point donné.

**Mise en forme et export**
- Plusieurs fonds de carte, masque France, gestion de l'ordre des couches.
- Modes de vue prédéfinis qui n'affichent que les outils utiles à une tâche
  (standard, mise en forme, données).
- Styles de carte personnalisés enregistrables et rechargeables.
- Export d'images de la carte et extraction des données, y compris en lot sur
  plusieurs points.

### Application PLU (`carte_plu.html`)

Interface plus légère, centrée sur l'urbanisme : saisie d'adresses, récupération de la
parcelle cadastrale correspondante, affichage du zonage PLU et des documents
d'urbanisme associés.

## Données et services externes

- **Mapbox GL JS** — rendu cartographique, géocodage, calculs d'itinéraires et isochrones.
- **API Carto (IGN)** — parcelles cadastrales et zones d'urbanisme.
- **Géoplateforme (IGN)** — fonds de plan et imagerie.
- **API Adresse et API Découpage administratif (data.gouv.fr)** — géocodage et
  référentiel communal.
- **Géoportail de l'urbanisme** — documents d'urbanisme.
- **Turf.js** — calculs géométriques côté navigateur.

Les couches du dossier `geojson/` sont chargées localement et ne dépendent d'aucun
service externe.

## Utilisation

Ouvrir `cartomax.html` dans un navigateur récent, saisir le mot de passe, puis
travailler depuis la barre latérale.

Les appels aux API externes et le chargement des fichiers du dossier `geojson/`
peuvent être bloqués par le navigateur si la page est ouverte directement depuis le
disque. En cas de couche qui ne s'affiche pas, servir le dossier via un petit serveur
HTTP local et ouvrir la page depuis `http://localhost`.

Une clé Mapbox est nécessaire au fonctionnement de la carte ; elle est intégrée dans
les pages.

## Préférences enregistrées

L'historique des recherches, la largeur de la barre latérale et l'état replié ou
déplié de chaque section sont conservés dans le stockage local du navigateur. Ces
préférences sont donc propres à chaque poste et à chaque navigateur, et disparaissent
si les données du navigateur sont effacées.
