﻿var builder = WebApplication.CreateBuilder();

builder.DisableIpPortBinding();

builder.Configuration
    .AddServiceConfiguration();

builder.Host
    .SetupSerilog(builder.Configuration);

builder.Services
    .RegisterMassTransit()
    .AddServiceConfiguration()
    .AddDatabase();

var app = builder.Build();
app.Run();
