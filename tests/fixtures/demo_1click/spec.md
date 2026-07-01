# One-Click Checkout Feature

## Objective
Allow returning customers to complete a purchase with a single button click,
using their saved payment method and default shipping address.

## Business Rules
- Feature is only available to registered users with a saved payment method
- Users must explicitly opt-in to save a payment method
- One-click purchase uses the most recently used payment method by default
- Users can change the default payment method in their account settings
- An order confirmation email is sent within 2 minutes of purchase
- Orders placed via one-click follow the same cancellation policy as regular orders

## Edge Cases
- If the saved payment method has expired, the user is redirected to the regular checkout
- If the default shipping address is undeliverable, the order is held pending address confirmation
- Double-clicks within 3 seconds are treated as a single click (debounce)
- If the payment processor is unavailable, the user sees a clear error and is redirected to regular checkout
