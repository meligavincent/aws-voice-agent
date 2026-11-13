"""Regenerate the reviewable CloudFormation Lex template; no cloud calls."""

import hashlib
import json
from pathlib import Path


def prompt(text):
    return {
        "MaxRetries": 2,
        "MessageGroupsList": [{"Message": {"PlainTextMessage": {"Value": text}}}],
    }


def locale(code, voice, sentences):
    intents = []
    for name, samples in sentences.items():
        intent = {"Name": name, "FulfillmentCodeHook": {"Enabled": True}}
        if name == "FallbackIntent":
            intent["ParentIntentSignature"] = "AMAZON.FallbackIntent"
        else:
            intent["SampleUtterances"] = [{"Utterance": s} for s in samples]
        if name in ("ClaimStatus", "RequestCallback"):
            intent["Slots"] = [
                {
                    "Name": n,
                    "SlotTypeName": "AMAZON.Number",
                    "ObfuscationSetting": {
                        "ObfuscationSettingType": "DefaultObfuscation"
                        if n == "AccessCode"
                        else "None"
                    },
                    "ValueElicitationSetting": {
                        "SlotConstraint": "Required",
                        "PromptSpecification": prompt(t),
                    },
                }
                for n, t in [
                    (
                        "ClaimNumber",
                        "Votre numéro de dossier à six chiffres ?"
                        if code == "fr_FR"
                        else "Your six-digit claim number?",
                    ),
                    (
                        "AccessCode",
                        "Votre code d’accès à six chiffres ?"
                        if code == "fr_FR"
                        else "Your six-digit access code?",
                    ),
                ]
            ]
            intent["SlotPriorities"] = [
                {"Priority": i + 1, "SlotName": n}
                for i, n in enumerate(["ClaimNumber", "AccessCode"])
            ]
        if name == "RequestCallback":
            intent["IntentConfirmationSetting"] = {
                "PromptSpecification": prompt(
                    "Confirmez-vous la demande de rappel ?"
                    if code == "fr_FR"
                    else "Do you confirm the callback request?"
                ),
                "DeclinationResponse": {
                    "MessageGroupsList": [
                        {
                            "Message": {
                                "PlainTextMessage": {
                                    "Value": "Demande annulée."
                                    if code == "fr_FR"
                                    else "Request cancelled."
                                }
                            }
                        }
                    ]
                },
            }
        intents.append(intent)
    return {
        "LocaleId": code,
        "NluConfidenceThreshold": 0.6,
        "VoiceSettings": {"VoiceId": voice},
        "Intents": intents,
    }


locales = [
    locale(
        "fr_FR",
        "Celine",
        {
            "ClaimStatus": [
                "où en est mon dossier",
                "suivre mon sinistre",
                "consulter mon dossier",
            ],
            "RequestCallback": ["je souhaite être rappelé", "demander un rappel"],
            "Handoff": ["parler à un conseiller", "un humain s'il vous plaît"],
            "FallbackIntent": [],
        },
    ),
    locale(
        "en_GB",
        "Amy",
        {
            "ClaimStatus": ["check my claim status", "track my claim"],
            "RequestCallback": ["request a callback", "please call me back"],
            "Handoff": ["speak to an advisor", "talk to a human"],
            "FallbackIntent": [],
        },
    ),
]
version_key = (
    "Version" + hashlib.sha256(json.dumps(locales, sort_keys=True).encode()).hexdigest()[:12]
)
resources = {
    "Bot": {
        "Type": "AWS::Lex::Bot",
        "Properties": {
            "Name": {"Ref": "BotName"},
            "RoleArn": {"Ref": "RoleArn"},
            "DataPrivacy": {"ChildDirected": False},
            "IdleSessionTTLInSeconds": 300,
            "AutoBuildBotLocales": True,
            "BotLocales": locales,
        },
    },
    version_key: {
        "Type": "AWS::Lex::BotVersion",
        "Properties": {
            "BotId": {"Ref": "Bot"},
            "BotVersionLocaleSpecification": [
                {
                    "LocaleId": loc["LocaleId"],
                    "BotVersionLocaleDetails": {"SourceBotVersion": "DRAFT"},
                }
                for loc in locales
            ],
        },
    },
    "Alias": {
        "Type": "AWS::Lex::BotAlias",
        "Properties": {
            "BotAliasName": "live",
            "BotId": {"Ref": "Bot"},
            "BotVersion": {"Fn::GetAtt": [version_key, "BotVersion"]},
            "BotAliasLocaleSettings": [
                {
                    "LocaleId": loc["LocaleId"],
                    "BotAliasLocaleSetting": {
                        "Enabled": True,
                        "CodeHookSpecification": {
                            "LambdaCodeHook": {
                                "CodeHookInterfaceVersion": "1.0",
                                "LambdaArn": {"Ref": "LambdaArn"},
                            }
                        },
                    },
                }
                for loc in locales
            ],
        },
    },
    "ConnectPolicy": {
        "Type": "AWS::Lex::ResourcePolicy",
        "Properties": {
            "ResourceArn": {"Fn::GetAtt": ["Alias", "Arn"]},
            "Policy": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "connect.amazonaws.com"},
                        "Action": ["lex:RecognizeText", "lex:StartConversation"],
                        "Resource": {"Fn::GetAtt": ["Alias", "Arn"]},
                        "Condition": {
                            "StringEquals": {"AWS:SourceAccount": {"Ref": "AWS::AccountId"}},
                            "ArnEquals": {"AWS:SourceArn": {"Ref": "ConnectArn"}},
                        },
                    }
                ],
            },
        },
    },
    "Association": {
        "Type": "AWS::Connect::IntegrationAssociation",
        "DependsOn": "ConnectPolicy",
        "Properties": {
            "InstanceId": {"Ref": "ConnectArn"},
            "IntegrationType": "LEX_BOT",
            "IntegrationArn": {"Fn::GetAtt": ["Alias", "Arn"]},
        },
    },
}
template = {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Description": "Bilingual Lex V2 bot with scoped Amazon Connect association; no conversation logs",
    "Parameters": {
        key: {"Type": "String"} for key in ["BotName", "RoleArn", "LambdaArn", "ConnectArn"]
    },
    "Resources": resources,
    "Outputs": {
        "AliasArn": {"Value": {"Fn::GetAtt": ["Alias", "Arn"]}},
        "BotId": {"Value": {"Ref": "Bot"}},
        "AliasId": {"Value": {"Fn::GetAtt": ["Alias", "BotAliasId"]}},
    },
}
Path("infra/modules/regional/templates/voice.json").write_text(
    json.dumps(template, indent=2, ensure_ascii=False) + "\n"
)
