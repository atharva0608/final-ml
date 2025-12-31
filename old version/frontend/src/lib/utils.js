import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Utility function for combining Tailwind CSS classes
 *
 * This function merges class names intelligently, handling:
 * - Conditional classes (via clsx)
 * - Tailwind class conflicts (via twMerge)
 *
 * Example usage:
 *   cn('px-2 py-1', isActive && 'bg-blue-500', 'text-white')
 *
 * @param {...any} inputs - Class names to combine
 * @returns {string} Merged class string
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
