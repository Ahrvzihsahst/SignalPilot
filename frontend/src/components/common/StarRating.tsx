import { Star } from 'lucide-react';
import { cn } from '@/utils/cn';

interface StarRatingProps {
  stars: number;
  maxStars?: number;
}

export function StarRating({ stars, maxStars = 5 }: StarRatingProps) {
  return (
    <div className="inline-flex gap-0.5" aria-label={`${stars} out of ${maxStars} stars`}>
      {Array.from({ length: maxStars }, (_, i) => (
        <Star
          key={i}
          className={cn(
            'h-4 w-4',
            i < stars ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'
          )}
        />
      ))}
    </div>
  );
}
