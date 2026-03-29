# Beat triggers at billing date
#     → Worker spins up its own session
#         → ContractRepository — fetch contract + details + tariffs
#         → DynamoDB — fetch timeseries data for billing period
#             → compute line items (apply correct tariff slot per reading)
#             → compute meter data totals
#             → compute energy mix
#                 → InvoiceRepository — create invoice + line items + meter data
#                     → Mailer — send invoice email
#                         → InvoiceRepository — create invoice history (success/fail)
