# Démarrage rapide

Ce dépôt implémente un agent de service client pour le suivi de sinistres fictifs. Il consulte un statut après vérification d’accès, enregistre une demande de rappel confirmée et répond à une FAQ publique. Il ne prend aucune décision d’indemnisation.

## Démonstration sur ton ordinateur

```bash
make setup
make local-up local-apply
make demo
make integration
```

Docker Engine doit fonctionner ; le Makefile sélectionne le contexte `default`, sans modifier le contexte global de ta machine. Le conteneur du projet utilise uniquement `127.0.0.1:4566`. Si un autre LocalStack occupe déjà ce port, arrête uniquement celui que tu as identifié ou adapte la configuration avant de lancer la démo.

La démonstration utilise le dossier fictif **123456** et le code **654321**. Elle invoque les vrais processus Lambda dans Docker et vérifie le trajet DynamoDB → Streams → Lambda → SQS → Lambda. Elle n’effectue aucun appel téléphonique. La réponse de FAQ locale est simulée et ne constitue pas un test Bedrock.

Les demandes de rappel créent un ticket dans DynamoDB : elles ne déclenchent pas un appel sortant et ne sont pas encore reliées à un CRM externe.

```bash
make check validate                  # qualité, tests, validation d’infrastructure
terraform -chdir=infra/aws test       # plans simulés une et deux régions
uv run voice-agent reconcile          # lecture seule : travaux en attente
uv run voice-agent reconcile --apply  # republication locale, traitement idempotent
make local-down                       # arrête uniquement les conteneurs de ce projet
```

## Passage à AWS

Suis le [guide détaillé](aws-deployment.md). Le code et les ressources sont prêts à être configurés et validés dans ton compte. Les identifiants AWS seuls ne suffisent pas : il faut également l’accès au modèle choisi, un numéro Amazon Connect, une file de conseillers configurée et alimentée, puis des tests vocaux réels.

La seconde région est optionnelle. Le basculement téléphonique Global Resiliency dépend de l’éligibilité et du paramétrage AWS : il n’est pas activé implicitement par Terraform.

Le code d’accès à six chiffres est un mécanisme de démonstration. Pour de vrais dossiers clients, il faut intégrer le système d’identité de l’entreprise et sa procédure de vérification. Le dépôt ne revendique pas de conformité réglementaire ni de résultats clients mesurés.
