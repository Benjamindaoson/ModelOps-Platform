"""Production preflight tests; safe config is a fixture, not production proof."""
import unittest
from preflight import merge,unsafe_secret,validate

def minimal_safe():
    return {
        "models":[{"name":"qwen-0.5b","source":"Qwen/Qwen2.5-0.5B-Instruct","replicas":2}],
        "litellm":{
            "enabled":True,"masterKey":"","existingSecret":"modelops-litellm-auth",
            "ui":{"password":""},
            "postgresql":{"enabled":True,"existingSecret":"modelops-litellm-db",
                          "auth":{"password":""},"extraDatabases":[]},
        },
        "keycloak":{"enabled":False},"langfuse":{"enabled":False},
        "security":{"enabled":True},"finetune":{"enabled":False},
    }

class PreflightTests(unittest.TestCase):
    def test_minimal_secure_values(self):
        self.assertEqual(validate(minimal_safe()),[])
    def test_production_placeholder_fail(self):
        data=minimal_safe()
        data["models"][0]["source"]="your-org/your-model"
        self.assertTrue(validate(data))
    def test_literal_key_fail(self):
        data=minimal_safe()
        data["litellm"]["masterKey"]="sk-this-secret-must-not-be-in-helm-values"
        self.assertTrue(any("masterKey" in x for x in validate(data)))
    def test_inline_db_password_fail(self):
        data=minimal_safe()
        data["litellm"]["postgresql"]["auth"]["password"]="secret"
        self.assertTrue(any("inline" in x for x in validate(data)))
    def test_unprotected_cluster_fail(self):
        data=minimal_safe()
        data["security"]["enabled"]=False
        self.assertTrue(validate(data))
    def test_unprotected_train_to_prod_fail(self):
        data=minimal_safe()
        data["finetune"]={"enabled":True,"evaluation":{"minSamples":20},
                            "deploy":{"auto":True}}
        self.assertTrue(any("auto" in x for x in validate(data)))
    def test_config_override_order(self):
        self.assertEqual(merge({"a":{"b":1,"c":2}},{"a":{"b":3}})["a"],{"b":3,"c":2})

if __name__=="__main__":
    unittest.main()
