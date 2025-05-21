   // src/components/ThemeController.tsx
   'use client';

   import { useEffect } from 'react';

   interface ThemeControllerProps {
     mode?: 'light' | 'dark'; // Mode from page config, defaults to 'light'
   }

   /**
    * A client component that dynamically adds or removes the 'dark' class
    * from the HTML element based on the provided mode.
    */
   export default function ThemeController({ mode = 'light' }: ThemeControllerProps) {
     useEffect(() => {
       const rootHtmlElement = document.documentElement;

       if (mode === 'dark') {
         rootHtmlElement.classList.add('dark');
       } else {
         rootHtmlElement.classList.remove('dark');
       }
     }, [mode]); // Re-run effect if 'mode' prop changes

     return null;
   }
