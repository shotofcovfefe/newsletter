// lib/emailTemplates.ts
// Contains functions to generate email content (HTML and Text).

/**
 * Generates the HTML and Text content for the subscription confirmation email.
 * @param confirmLink
 * @returns
 */
export function generateConfirmationEmailContent(confirmLink: string): { html: string; text: string } {
    const emailSubject = 'Confirm your Unfog London subscription';

    // Nicely formatted HTML Email Body
    const emailHtml = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="x-ua-compatible" content="ie=edge">
  <title>${emailSubject}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style type="text/css">
    /* Basic resets and styles for better email client compatibility */
    body, table, td, a { -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
    table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; border-collapse: collapse; }
    img { -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }
    body { height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; background-color: #f8f9fa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol'; }
    a { color: #10b981; /* Emerald-500 */ text-decoration: underline; }
    a[x-apple-data-detectors] { color: inherit !important; text-decoration: none !important; font-size: inherit !important; font-family: inherit !important; font-weight: inherit !important; line-height: inherit !important; }
    .button-link { background-color: #10b981; border-radius: 6px; color: #ffffff !important; display: inline-block; font-size: 16px; font-weight: bold; line-height: 1.5; padding: 12px 24px; text-align: center; text-decoration: none; -webkit-text-size-adjust: none; mso-hide: all; }
    .container { max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    .content { padding: 30px 40px; text-align: left; color: #343a40; font-size: 16px; line-height: 1.6; }
    .content-center { text-align: center; }
    .footer { font-size: 12px; color: #868e96; text-align: center; margin-top: 20px; padding: 20px 40px; background-color: #f1f3f5; border-top: 1px solid #dee2e6;}
    h1 { font-size: 24px; font-weight: 600; color: #212529; margin-bottom: 15px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="content">
      <h1>Almost there!</h1>
      <p>Hi there,</p>
      <p>Thanks for your interest in the <strong>Unfog London</strong> newsletter! We're excited to help you discover happenings tailored just for you.</p>
      <p>To complete your subscription and start receiving curated event suggestions, please confirm your email address by clicking the button below:</p>
      <p class="content-center" style="margin: 30px 0;">
        <a href="${confirmLink}" target="_blank" class="button-link" style="color: #ffffff !important;">Confirm Email Address</a>
      </p>
      <p>If the button doesn't work, you can also copy and paste this link into your browser's address bar:</p>
      <p style="font-size: 12px; word-break: break-all;"><a href="${confirmLink}" target="_blank">${confirmLink}</a></p>
      <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">
      <p style="font-size: 14px; color: #6c757d;">If you didn't sign up for this newsletter, you can safely ignore this email. Your address won't be subscribed.</p>
    </div>
    <div class="footer">
      Unfog London
    </div>
  </div>
</body>
</html>
    `;

    // Plain Text Version
    const emailText = `
Almost there!

Hi there,

Thanks for your interest in the Unfog London newsletter!

To complete your subscription, please confirm your email address by visiting the link below:

${confirmLink}

If you didn't sign up for this newsletter, please ignore this email.

- Unfog London
    `;

    return { html: emailHtml, text: emailText };
}