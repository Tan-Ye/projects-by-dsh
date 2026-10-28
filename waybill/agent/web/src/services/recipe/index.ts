/** 配方接口。 */

import { get } from '@/services/http'
import type { RecipeListResult } from './interface'

export async function listRecipes(): Promise<RecipeListResult> {
  return get<RecipeListResult>('/api/recipes')
}
