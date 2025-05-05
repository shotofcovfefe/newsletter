// app/layout.tsx
import './globals.css'
import { Inter, EB_Garamond } from 'next/font/google'
import Header from '@/components/Header'
import Footer from '@/components/Footer'
import FogOverlay from '@/components/FogOverlay' // Assuming this is positioned correctly relative to its container

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const garamond = EB_Garamond({ subsets: ['latin'], variable: '--font-garamond' })

export const metadata = {
  title: 'Unfog London', // <-- Updated Title
  description: 'Curated London events, tailored to your postcode and interests.', // <-- Updated Description
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${garamond.variable}`}>
      {/* Apply flex layout and min-height to body to enable sticky footer */}
      <body className="font-sans bg-white dark:bg-[#0A0A0A] text-black dark:text-white
                       relative transition-colors duration-300
                       flex flex-col min-h-screen"> {/* <-- ADDED flex setup */}

        <Header /> {/* Header stays at the top */}

        {/* This wrapper div now grows to fill available space */}
        {/* The FogOverlay's positioning depends on its own CSS. Relative here contains it unless it's fixed/absolute to viewport */}
        <div className="relative z-10 flex-grow w-full"> {/* <-- ADDED flex-grow and w-full */}
          {/* The 'children' (including page.tsx's <main>) render here */}
          {/* <main> tag from page.tsx will be inside this div */}
          {children}
          {/* FogOverlay might need specific styling if it should cover header/footer */}
          <FogOverlay />
        </div>

        <Footer /> {/* Footer is pushed down by the flex-grow div above */}

      </body>
    </html>
  )
}