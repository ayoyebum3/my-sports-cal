# Calendrier sportif personnel

Un calendrier `.ics` qui se met à jour tout seul deux fois par jour et auquel
Calendrier d'Apple s'abonne. Aucun service tiers : un script lit les horaires
aux sources (API officielle de la LNH, données publiques d'ESPN, liste
manuelle) et GitHub publie le fichier gratuitement.

## Contenu par défaut

| Catégorie | Source | Mise à jour |
|---|---|---|
| Canadiens (saison + séries) | API LNH | automatique, scores finaux inclus |
| Finale de la Coupe Stanley | API LNH | automatique, dès que programmée |
| Sunday Night Football + séries NFL + Super Bowl | ESPN | automatique |
| Finales NBA, WNBA, Série mondiale, Coupe MLS | ESPN | automatique, dès que programmées |
| Cyclisme (Grands Tours, Monuments, GP Québec/Montréal) | `config.yaml` | à la main, une fois par an |
| LPHF (Coupe Walter) | `config.yaml` | à la main (aucune source ouverte fiable) |

Tout se règle dans **`config.yaml`** : activer/désactiver une source,
ajouter une équipe complète (exemple CF Montréal en commentaire), ajouter
des événements à la main.

## Installation (une seule fois, ~15 min)

### 1. Créer le dépôt GitHub
1. Crée un compte sur github.com (gratuit) si ce n'est pas fait.
2. **New repository** → nom : `calendrier-sports` → **Public** → Create.
   (Public est nécessaire pour GitHub Pages sur le forfait gratuit. Le
   dépôt ne contient aucune donnée personnelle.)
3. **Add file → Upload files** → glisse le contenu du dossier décompressé.
   ⚠️ Le dossier `.github` est caché dans le Finder : appuie sur
   **Cmd + Maj + .** pour l'afficher avant de glisser. S'il manque,
   rien ne se mettra à jour.

### 2. Activer la publication
1. Dans le dépôt : **Settings → Pages → Source : GitHub Actions**.
2. Onglet **Actions** → « Mettre à jour le calendrier » → **Run workflow**.
3. Après 1–2 minutes, la page `https://TON-NOM.github.io/calendrier-sports/`
   affiche l'adresse du calendrier.

### 3. S'abonner (synchronisé sur tous tes appareils)
**Sur un Mac** (méthode à privilégier) :
Calendrier → **Fichier → Nouvel abonnement à un calendrier** → colle
l'adresse `.../sports.ics` → **Emplacement : iCloud** → Actualisation
automatique : « Toutes les heures ». Le calendrier apparaît ensuite sur
l'iPhone, l'iPad et la Montre.

**Sans Mac** : sur l'iPhone, Réglages → Apps → Calendrier → Comptes →
Ajouter un compte → Autre → Ajouter un calendrier avec abonnement.
Attention : ajouté ainsi, il reste sur cet appareil seulement.

## Modifier le calendrier
Ouvre `config.yaml` sur github.com, clique sur le crayon, modifie, puis
**Commit changes**. Le calendrier est régénéré dans la minute; Apple le
récupère à sa prochaine actualisation.

## Limites à connaître
- **Fréquence** : c'est Apple qui décide quand relire le fichier
  (généralement quelques heures au plus). Un match déplacé le jour même
  peut donc apparaître en retard.
- **Alertes** : Calendrier retire par défaut les alertes des calendriers
  abonnés. Si tu en veux, active les alertes par défaut pour ce
  calendrier dans les réglages de Calendrier.
- **ESPN** n'a pas d'API officielle documentée. Si son format change, la
  source concernée échoue; le script garde alors les événements de la
  version précédente au lieu de les effacer, et l'onglet Actions affiche
  l'erreur (GitHub t'envoie un courriel).
- **Finales** : elles n'apparaissent qu'une fois programmées par les
  ligues, d'abord avec des équipes « À déterminer ».
- **Sunday Night Football** : détecté comme le match du dimanche commençant
  à 19 h ou plus tard (heure de Montréal). Les matchs « flexés » à la
  dernière minute se corrigent à la mise à jour suivante.
- Les noms d'équipes et les réseaux de diffusion venant d'ESPN sont en
  anglais et américains; ceux des Canadiens sont canadiens (RDS, TVA, SN).
- **Inactivité** : GitHub suspend les tâches planifiées des dépôts
  inactifs depuis 60 jours. Le flux de travail fait un commit vide le 1er
  de chaque mois pour l'éviter.
