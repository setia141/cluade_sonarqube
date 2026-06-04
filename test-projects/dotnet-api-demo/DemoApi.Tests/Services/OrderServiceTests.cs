using DemoApi.Services;
using Microsoft.Extensions.Configuration;
using Moq;
using System.Net;
using System.Net.Http.Json;

namespace DemoApi.Tests.Services;

public class OrderServiceTests
{
    [Fact]
    public async Task CancelOrderAsync_ReturnsFalse_WhenServiceReturns404()
    {
        var handler = new MockHttpMessageHandler(HttpStatusCode.NotFound);
        var client  = new HttpClient(handler);
        var config  = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> {
                ["Services:Payment:BaseUrl"] = "http://payment-mock"
            })
            .Build();

        var service = new OrderService(client, config);
        var result  = await service.CancelOrderAsync("order-1");

        Assert.False(result);
    }

    // NOTE: ProcessOrderAsync and GetPaymentStatusAsync are NOT tested.
    // The agent will detect uncovered lines and create tests for them.
}

// Minimal mock handler for unit tests
public class MockHttpMessageHandler : HttpMessageHandler
{
    private readonly HttpStatusCode _statusCode;
    public MockHttpMessageHandler(HttpStatusCode statusCode) => _statusCode = statusCode;

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken cancellationToken)
        => Task.FromResult(new HttpResponseMessage(_statusCode));
}
