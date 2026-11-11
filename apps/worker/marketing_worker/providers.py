class ProviderNotConfigured(RuntimeError):
    code = 'provider_not_configured'


class UnconfiguredProvider:
    def submit(self, *args, **kwargs):
        raise ProviderNotConfigured('服务商、模型、价格及数据授权尚未配置，未发起外部调用。')

    def query(self, *args, **kwargs):
        raise ProviderNotConfigured('尚未配置供应商查询接口。')

    def cancel(self, *args, **kwargs):
        raise ProviderNotConfigured('尚未配置供应商取消接口；不能据此释放未知费用预留。')
