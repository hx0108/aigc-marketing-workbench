import httpx
import pytest
from marketing_worker.http_providers import HTTPProvider, ExternalUnknown
from marketing_worker.pipeline import failure_details

@pytest.mark.parametrize('error_type',[httpx.ReadTimeout,httpx.ConnectError,httpx.ProxyError])
def test_transport_type_preserved_without_request_secrets(error_type):
    calls=[]
    def handle(request):
        calls.append(request)
        raise error_type('SECRET URL https://private.invalid?key=SECRET',request=request)
    provider=HTTPProvider('SECRET','https://provider.example','model',httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ExternalUnknown) as caught:provider.request('POST','/generate',{'private':'SECRET'})
    assert failure_details(caught.value)=={'code':'external_unknown','transport_error':error_type.__name__}
    assert 'SECRET' not in str(caught.value)
    assert len(calls)==1

def test_http_503_preserved_without_response_body():
    provider=HTTPProvider('SECRET','https://provider.example','model',httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(503,text='SECRET'))))
    with pytest.raises(ExternalUnknown) as caught:provider.request('POST','/generate')
    assert failure_details(caught.value)=={'code':'external_unknown','provider_status':503}

def test_diagnostic_values_are_allowlisted():
    assert failure_details(ExternalUnknown('failure',status_code='SECRET',transport_error='SECRET'))=={'code':'external_unknown'}
