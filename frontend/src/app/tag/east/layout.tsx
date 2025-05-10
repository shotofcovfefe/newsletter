// src/app/(marketing)/east-london/layout.tsx
import React from 'react';

// This layout component will wrap the East London page.
// It's responsible for setting the unique background and ensuring content fills the space.
export default function EastLondonLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // This div will apply the gradient background and ensure it fills the area
    // provided by the RootLayout's flex-grow container.
    // It uses flex flex-col to allow its own children (the page content) to be structured.
    <div className="bg-gradient-to-br from-slate-50 to-sky-100 text-neutral-800 w-full flex-grow flex flex-col">
      {/* The children prop will render the EastLondonPage component */}
      {children}
    </div>
  );
}
