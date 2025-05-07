// src/components/ContactForm.tsx
'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useState } from 'react';
import dynamic from 'next/dynamic';

const Turnstile = dynamic(
  () => import('@marsidev/react-turnstile').then(m => m.Turnstile),
  { ssr: false }
);

const contactFormSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Please enter a valid email address'),
  subject: z.string().min(3, 'Subject must be at least 3 characters').optional(),
  message: z.string().min(10, 'Message must be at least 10 characters'),
  cfToken: z.string().min(1, { message: "Please complete the CAPTCHA." }),
});

type ContactFormData = z.infer<typeof contactFormSchema>;

export default function ContactForm() {
  const [formStatus, setFormStatus] = useState<{ type: 'idle' | 'loading' | 'success' | 'error'; message: string }>({ type: 'idle', message: '' });

  const {
    register,
    handleSubmit,
    setValue,
    reset, // To clear the form after successful submission
    formState: { errors, isSubmitting },
  } = useForm<ContactFormData>({
    resolver: zodResolver(contactFormSchema),
    defaultValues: {
      name: '',
      email: '',
      subject: '',
      message: '',
      cfToken: '',
    }
  });

  const setToken = (token: string | null) => {
    setValue('cfToken', token || '', { shouldValidate: true });
  };

  const onSubmit = async (data: ContactFormData) => {
    setFormStatus({ type: 'loading', message: 'Sending...' });
    try {
      const response = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const result = await response.json();

      if (response.ok) {
        setFormStatus({ type: 'success', message: 'Message sent successfully! I will get back to you soon.' });
        reset(); // Clear the form
      } else {
        setFormStatus({ type: 'error', message: result.error || 'Failed to send message. Please try again.' });
      }
    } catch (error) {
      console.error('Contact form submission error:', error);
      setFormStatus({ type: 'error', message: 'An unexpected error occurred. Please try again later.' });
    }
  };

  // Define a consistent minimum height for error message placeholders
  const errorPlaceholderHeight = "min-h-[20px]";

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-6 bg-white dark:bg-neutral-800/50 p-6 sm:p-8 rounded-lg shadow-md"
    >
      <div>
        <label htmlFor="name" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          Your Name
        </label>
        <input
          id="name"
          type="text"
          {...register('name')}
          className={`w-full p-3 rounded border ${errors.name ? 'border-red-500' : 'border-neutral-300 dark:border-neutral-600'} bg-neutral-50 dark:bg-neutral-700 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500`}
        />
        <div className={errorPlaceholderHeight}>
          {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name.message}</p>}
        </div>
      </div>

      <div>
        <label htmlFor="email" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          Your Email
        </label>
        <input
          id="email"
          type="email"
          {...register('email')}
          className={`w-full p-3 rounded border ${errors.email ? 'border-red-500' : 'border-neutral-300 dark:border-neutral-600'} bg-neutral-50 dark:bg-neutral-700 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500`}
        />
        <div className={errorPlaceholderHeight}>
          {errors.email && <p className="text-xs text-red-500 mt-1">{errors.email.message}</p>}
        </div>
      </div>

      <div>
        <label htmlFor="subject" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          Subject (Optional)
        </label>
        <input
          id="subject"
          type="text"
          {...register('subject')}
          className={`w-full p-3 rounded border ${errors.subject ? 'border-red-500' : 'border-neutral-300 dark:border-neutral-600'} bg-neutral-50 dark:bg-neutral-700 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500`}
        />
        <div className={errorPlaceholderHeight}>
         {errors.subject && <p className="text-xs text-red-500 mt-1">{errors.subject.message}</p>}
        </div>
      </div>

      <div>
        <label htmlFor="message" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          Message
        </label>
        <textarea
          id="message"
          rows={5}
          {...register('message')}
          className={`w-full p-3 rounded border ${errors.message ? 'border-red-500' : 'border-neutral-300 dark:border-neutral-600'} bg-neutral-50 dark:bg-neutral-700 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500`}
        />
        <div className={errorPlaceholderHeight}>
         {errors.message && <p className="text-xs text-red-500 mt-1">{errors.message.message}</p>}
        </div>
      </div>

      <div>
        <Turnstile
          siteKey={process.env.NEXT_PUBLIC_CF_SITE_KEY!} // Ensure this is set in your .env.local
          onSuccess={setToken}
          options={{ theme: 'auto' }}
        />
         <div className={errorPlaceholderHeight}>
          {errors.cfToken && <p className="text-xs text-red-500 mt-1">{errors.cfToken.message}</p>}
        </div>
      </div>

      <div>
        <button
          type="submit"
          disabled={isSubmitting || formStatus.type === 'loading'}
          className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3 px-4 rounded-md font-semibold transition duration-150 ease-in-out disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSubmitting || formStatus.type === 'loading' ? 'Sending...' : 'Send Message'}
        </button>
      </div>

      {formStatus.type === 'success' && (
        <p className="text-sm text-emerald-600 dark:text-emerald-400 p-3 bg-emerald-50 dark:bg-emerald-900/30 rounded-md">{formStatus.message}</p>
      )}
      {formStatus.type === 'error' && (
        <p className="text-sm text-red-600 dark:text-red-400 p-3 bg-red-50 dark:bg-red-900/30 rounded-md">{formStatus.message}</p>
      )}
    </form>
  );
}