import unittest

from verify_canary_routing import CanaryCheckError, origin_only, owned_model_ids, verify

def metadata():
    return {"data":[
        {"model_name":"alpha--qwen","model_info":{"id":"stable-1",
            "metadata":{"owner":"modelops","namespace":"alpha","resource":"qwen","slot":"stable"}}},
        {"model_name":"alpha--qwen","model_info":{"id":"canary-1",
            "metadata":{"owner":"modelops","namespace":"alpha","resource":"qwen","slot":"canary"}}},
    ]}

def transport_with_cycle(n_canary):
    counter={"index":0}
    def callback(url,key,payload=None):
        if url.endswith("/model/info"):
            return {},metadata()
        i=counter["index"]
        counter["index"]+=1
        chosen="canary-1" if i < n_canary else "stable-1"
        return {"x-litellm-model-id":chosen},{"choices":[{"message":{"content":"OK"}}]}
    return callback

class CanaryHTTPContracts(unittest.TestCase):
    def test_measured_20_percent_real_http_contract(self):
        result=verify("http://127.0.0.1:4000","key","alpha--qwen",20,100,
                      transport=transport_with_cycle(20))
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(result["measured_canary_percent"],20)
        self.assertEqual(result["requests"],100)

    def test_unexpected_distribution_fails(self):
        result=verify("http://127.0.0.1:4000","key","alpha--qwen",20,100,
                      transport=transport_with_cycle(100))
        self.assertEqual(result["status"],"FAIL_DISTRIBUTION")

    def test_missing_deployment_header_is_not_positive_evidence(self):
        def bad(url,key,payload=None):
            if url.endswith("/model/info"):
                return {},metadata()
            return {},{"choices":[{"message":{"content":"OK"}}]}
        with self.assertRaisesRegex(CanaryCheckError,"x-litellm-model-id"):
            verify("http://127.0.0.1:4000","key","alpha--qwen",20,100,transport=bad)

    def test_unmanaged_model_cannot_be_counted_as_canary(self):
        raw=metadata()
        raw["data"][1]["model_info"]["metadata"]["owner"]="manual"
        with self.assertRaises(CanaryCheckError):
            owned_model_ids(raw,"alpha--qwen")

    def test_credentials_in_url_rejected(self):
        with self.assertRaises(CanaryCheckError):
            origin_only("http://owner:secret@localhost:4000")


if __name__=="__main__":
    unittest.main()
