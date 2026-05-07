"""
Copyright (c) Truveta. All rights reserved.

Constants used by exchange config orchestration.
"""

OPENLINKTOKEN_EXCHANGE_JWE_MODULE = "openlinktoken.exchange_jwe"
OPENLINKTOKEN_EXCHANGE_CONFIG_MODULE = "openlinktoken.exchange_config"

PEM_HEADER_PREFIX = "-----"
JWE_RECIPIENT_ALG = "ECDH-ES+A256KW"
EC_KEY_TYPE = "EC"
P256_CURVE = "P-256"
KID_SHA256_PREFIX = "sha256:"

EXCHANGE_NAME_KEY = "exchangeName"
EXCHANGE_ID_KEY = "exchangeId"
HASHING_SECRET_KEY = "hashingSecret"
HASHING_SECRET_ENCODING_KEY = "hashingSecretEncoding"
SERVER_PUBLIC_KEY_KEY = "serverPublicKey"

ENCRYPTED_ROTATION_IV_KEY = "encryptedRotationIv"
ROTATION_IV_KEY = "rotationIv"
ROTATION_IV_ENCODING_KEY = "rotationIvEncoding"
ROTATION_IV_ENCODING_VALUE = "base64url"
ROTATION_COUNT_KEY = "rotationCount"
BIN_WIDTH_KEY = "binWidth"
DIMENSION_BIAS_KEY = "dimensionBias"
DEFAULT_ROTATION_COUNT = 30
DEFAULT_BIN_WIDTH = 0.05

REQUIRED_SERVER_RESPONSE_FIELDS = (
    EXCHANGE_NAME_KEY,
    EXCHANGE_ID_KEY,
    HASHING_SECRET_KEY,
    HASHING_SECRET_ENCODING_KEY,
    SERVER_PUBLIC_KEY_KEY,
)

OPENLINKTOKEN_CURVE_BY_CRYPTOGRAPHY_CURVE = {
    "secp256r1": "P-256",
    "secp384r1": "P-384",
    "secp521r1": "P-521",
}
