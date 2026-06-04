using System.Net.Http.Json;

namespace DemoApi.Services;

public class OrderResult
{
    public string? OrderId { get; set; }
    public string? PaymentId { get; set; }
    public bool Success { get; set; }
}

public class OrderService
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _config;

    public OrderService(HttpClient httpClient, IConfiguration config)
    {
        _httpClient = httpClient;
        _config = config;
    }

    // csharpsquid:S2259 — possible null dereference
    // ReadFromJsonAsync can return null but result is used without null check
    public async Task<OrderResult> ProcessOrderAsync(string customerId, decimal amount)
    {
        var response = await _httpClient.PostAsJsonAsync(
            _config["Services:Payment:BaseUrl"] + "/charge",
            new { customerId, amount }
        );
        response.EnsureSuccessStatusCode();

        var result = await response.Content.ReadFromJsonAsync<OrderResult>();
        return new OrderResult
        {
            OrderId   = Guid.NewGuid().ToString(),
            PaymentId = result.PaymentId,   // S2259: result may be null
            Success   = result.Success
        };
    }

    // csharpsquid:S3966 — object disposed more than once
    public async Task<string> GetPaymentStatusAsync(string paymentId)
    {
        var client = new HttpClient();
        try
        {
            var response = await client.GetAsync(
                _config["Services:Payment:BaseUrl"] + "/status/" + paymentId
            );
            response.EnsureSuccessStatusCode();
            client.Dispose();          // first dispose
            return await response.Content.ReadAsStringAsync();
        }
        finally
        {
            client.Dispose();          // S3966: second dispose
        }
    }

    // csharpsquid:S1481 — unused local variable
    public async Task<bool> CancelOrderAsync(string orderId)
    {
        string auditMessage = $"Cancelling order {orderId}";   // S1481: never used
        var response = await _httpClient.DeleteAsync(
            _config["Services:Payment:BaseUrl"] + "/orders/" + orderId
        );
        return response.IsSuccessStatusCode;
    }
}
