import re

from voice_agent.ai import Unavailable

TEXT = {
    "fr": {
        "auth": "Je ne peux pas vérifier votre accès. Je vous oriente vers un conseiller.",
        "handoff": "Je vous oriente vers un conseiller pour poursuivre votre demande.",
        "confirm": "Souhaitez-vous que je crée une demande de rappel pour ce dossier ?",
        "cancel": "La demande de rappel n’a pas été créée.",
        "callback": "Votre demande de rappel est enregistrée. Aucun délai de rappel ne peut être garanti ici.",
        "status": "Votre dossier est au statut : {status}. Pièces attendues : {missing}. Prochaine étape : {next_step}.",
        "claim": "Quel est votre numéro de dossier à six chiffres ?",
        "code": "Quel est votre code d’accès personnel à six chiffres ?",
    },
    "en": {
        "auth": "I could not verify your access. I will transfer you to an advisor.",
        "handoff": "I will transfer you to an advisor to continue your request.",
        "confirm": "Would you like me to create a callback request for this claim?",
        "cancel": "No callback request was created.",
        "callback": "Your callback request is recorded. I cannot guarantee a callback time.",
        "status": "Your claim status is: {status}. Missing documents: {missing}. Next step: {next_step}.",
        "claim": "What is your six-digit claim number?",
        "code": "What is your six-digit access code?",
    },
}


def slot_value(intent, name):
    value = (intent.get("slots") or {}).get(name) or {}
    return str(value.get("value", {}).get("interpretedValue", "")).strip()


def response(event, message, state="Fulfilled", action="Close", slot=None, handoff=False):
    original = event.get("sessionState", {}).get("intent", {})
    intent = {
        "name": original.get("name", "FallbackIntent"),
        "state": state,
        "slots": dict(original.get("slots") or {}),
    }
    # Do not echo the secret back in fulfillment responses or contact attributes.
    if action != "ElicitSlot" and "AccessCode" in intent["slots"]:
        intent["slots"]["AccessCode"] = None
    if action == "ConfirmIntent":
        intent["confirmationState"] = "None"
    dialog = {"type": action}
    if slot:
        dialog["slotToElicit"] = slot
        intent["slots"][slot] = None
    attributes = {"handoff": str(handoff).lower(), "last_intent": intent["name"]}
    return {
        "sessionState": {"dialogAction": dialog, "intent": intent, "sessionAttributes": attributes},
        "messages": [{"contentType": "PlainText", "content": message}],
    }


class Agent:
    def __init__(self, store, faq):
        self.store = store
        self.faq = faq

    def handle(self, event):
        lang = "en" if event.get("bot", {}).get("localeId", "fr_FR").startswith("en") else "fr"
        text = TEXT[lang]
        intent = event.get("sessionState", {}).get("intent", {})
        name = intent.get("name", "FallbackIntent")
        if name == "Handoff":
            return response(event, text["handoff"], handoff=True)
        if name in ("ClaimStatus", "RequestCallback"):
            claim_id = slot_value(intent, "ClaimNumber")
            code = slot_value(intent, "AccessCode")
            if not re.fullmatch(r"\d{6}", claim_id):
                return response(
                    event,
                    text["claim"],
                    state="InProgress",
                    action="ElicitSlot",
                    slot="ClaimNumber",
                )
            if not re.fullmatch(r"\d{6}", code):
                return response(
                    event, text["code"], state="InProgress", action="ElicitSlot", slot="AccessCode"
                )
            claim = self.store.authenticate(claim_id, code)
            if not claim:
                return response(event, text["auth"], state="Failed", handoff=True)
            if name == "ClaimStatus":
                details = claim.get(lang, claim.get("fr", {}))
                safe = {
                    k: str(details.get(k, "—"))[:300] for k in ("status", "missing", "next_step")
                }
                return response(event, text["status"].format(**safe))
            confirmation = intent.get("confirmationState", "None")
            if confirmation == "Denied":
                return response(event, text["cancel"])
            if confirmation != "Confirmed":
                # Keep the code for Lex's confirmation turn only; no persistence or logging.
                result = response(
                    event, text["confirm"], state="InProgress", action="ConfirmIntent"
                )
                result["sessionState"]["intent"]["slots"] = intent.get("slots", {})
                return result
            self.store.create_callback(event["sessionId"], claim)
            return response(event, text["callback"])
        question = event.get("inputTranscript", "")[:1200]
        # Personal claim questions must use the authenticated deterministic path.
        if re.search(r"\b\d{6}\b", question) or any(
            w in question.lower() for w in ("mon dossier", "my claim", "mon code", "access code")
        ):
            return response(event, text["handoff"], handoff=True)
        try:
            return response(event, self.faq.answer(question))
        except Unavailable:
            return response(event, text["handoff"], handoff=True)
