// lib/emailTemplates.ts
// Generate confirmation-email content (HTML + plain text) per newsletter.

type ColourSet = {
  /** CTA button + links */
  primary: string
  /** headings / decoration; optional */
  accent?: string
}

interface NewsletterTemplate {
  /** Email subject line */
  subject: string
  /** Brand colours */
  colour: ColourSet
  /** Brand / footer name (“Unfog London” etc.) */
  brandName: string
  /** Optional hero line under the heading */
  heroCopy?: string
}

/* ─────────────────────────────────────────────────────────
   Templates — add as many as you need; copy & tweak colours
   ───────────────────────────────────────────────────────── */
const templates: Record<string, NewsletterTemplate> = {
  /* generic / fallback */
  default: {
    subject   : 'Confirm your Unfog London subscription',
    brandName : 'Unfog London',
    colour    : { primary: '#10b981', accent: '#10b981' }, // emerald-500
    heroCopy  : "We're excited to help you discover happenings tailored just for you.",
  },

  /* example: art newsletter with red brand */
  art: {
    subject   : 'Confirm your Art Highlights subscription',
    brandName : 'Art Highlights • Unfog',
    colour    : { primary: '#ef4444', accent: '#ef4444' }, // red-500
    heroCopy  : 'The best exhibitions, openings and art events—curated for you.',
  },

  /* example: food newsletter with purple brand */
  food: {
    subject   : 'Confirm your London Food Scene subscription',
    brandName : 'Unfog Foodie',
    colour    : { primary: '#8b5cf6', accent: '#8b5cf6' }, // violet-500
    heroCopy  : 'Tastiest pop-ups, supper-clubs and restaurant news every week.',
  },
}

/* helper to make the HTML body */
function buildHtml(confirmLink: string, tpl: NewsletterTemplate): string {
  const { primary, accent = primary } = tpl.colour
  const encodedSubject = tpl.subject.replace(/"/g, '&quot;')

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="x-ua-compatible" content="ie=edge">
<title>${encodedSubject}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body,table,td,a{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}
table,td{mso-table-lspace:0;mso-table-rspace:0;border-collapse:collapse}
img{-ms-interpolation-mode:bicubic;border:0;height:auto;line-height:100%;outline:none;text-decoration:none}
body{height:100%!important;margin:0!important;padding:0!important;width:100%!important;background:#f8f9fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
a{color:${primary};text-decoration:underline}
a[x-apple-data-detectors]{color:inherit!important;text-decoration:none!important;font-size:inherit!important;font-family:inherit!important;font-weight:inherit!important;line-height:inherit!important}
.button-link{background:${primary};border-radius:6px;color:#ffffff!important;display:inline-block;font-size:16px;font-weight:bold;line-height:1.5;padding:12px 24px;text-align:center;text-decoration:none;-webkit-text-size-adjust:none;mso-hide:all}
.container{max-width:600px;margin:20px auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 4px 10px rgba(0,0,0,0.05)}
.content{padding:30px 40px;text-align:left;color:#343a40;font-size:16px;line-height:1.6}
.content-center{text-align:center}
.footer{font-size:12px;color:#868e96;text-align:center;margin-top:20px;padding:20px 40px;background:#f1f3f5;border-top:1px solid #dee2e6}
h1{font-size:24px;font-weight:600;color:#212529;margin-bottom:15px}
hr{border:none;border-top:1px solid #dee2e6;margin:30px 0}
</style>
</head>
<body>
<div class="container">
  <div class="content">
    <h1 style="color:${accent}">Almost there!</h1>
    <p>Hi there,</p>
    <p>${tpl.heroCopy ?? ''}</p>
    <p>To complete your subscription, please confirm your email address by clicking the button below:</p>
    <p class="content-center" style="margin:30px 0">
      <a href="${confirmLink}" target="_blank" class="button-link">Confirm Email Address</a>
    </p>
    <p>If the button doesn't work, copy &amp; paste this link into your browser:</p>
    <p style="font-size:12px;word-break:break-all"><a href="${confirmLink}" target="_blank">${confirmLink}</a></p>
    <hr>
    <p style="font-size:14px;color:#6c757d">If you didn't sign up for this newsletter, you can safely ignore this email.</p>
  </div>
  <div class="footer">${tpl.brandName}</div>
</div>
</body>
</html>`
}

/* helper for plain-text */
function buildText(confirmLink: string, tpl: NewsletterTemplate): string {
  return `Almost there!

Hi there,

${tpl.heroCopy ?? ''}

To complete your subscription, please confirm your email address:

${confirmLink}

If you didn't sign up for this newsletter, please ignore this email.

- ${tpl.brandName}
`
}

/* ─────────────────────────────────────────────────────────
   PUBLIC API — identical return shape to the old function
   ───────────────────────────────────────────────────────── */
export function generateConfirmationEmailContent(
  confirmLink: string,
  newsletter: keyof typeof templates = 'default',
): { html: string; text: string } {
  const tpl = templates[newsletter] ?? templates.default
  return {
    html : buildHtml(confirmLink, tpl),
    text : buildText(confirmLink, tpl),
  }
}

/** expose template metadata (e.g. subject lines) */
export { templates }
