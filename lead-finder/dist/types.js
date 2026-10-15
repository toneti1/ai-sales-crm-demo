import { z } from 'zod';
export const SegmentSchema = z.enum(['A', 'B']);
export const SizeSchema = z.enum(['micro', 'small', 'medium']);
export const PrioritySchema = z.enum(['high', 'medium', 'low']);
export const FactsSchema = z.object({
    siteDown: z.boolean(),
    https: z.boolean(),
    loadTimeMs: z.number(),
    pageWeightBytes: z.number(),
    jsErrors: z.number(),
    hasViewport: z.boolean(),
    mobileOverflow: z.boolean(),
    copyrightYear: z.number().nullable(),
    isOutdated: z.boolean(),
    lastContentDate: z.string().nullable(),
    cms: z.string().nullable(),
    legacyLibs: z.array(z.string()),
    formCount: z.number(),
    hasContactForm: z.boolean(),
    clickablePhone: z.boolean(),
    visibleEmail: z.boolean(),
    whatsapp: z.boolean(),
    bookingEngine: z.boolean(),
    ecommerce: z.boolean(),
    chatWidget: z.boolean(),
    hasChatbot: z.boolean(),
    newsletter: z.boolean(),
    menuPdf: z.boolean(),
    pricesVisible: z.boolean(),
    languages: z.array(z.string()),
});
export const PainPointSchema = z.object({
    fact: z.string(),
    issue: z.string(),
    impact: z.enum(['high', 'medium', 'low']),
});
export const OpportunitySchema = z.object({
    automation: z.string(),
    solvesFact: z.string(),
    pitchLine: z.string(),
});
export const AuditSchema = z.object({
    painPoints: z.array(PainPointSchema).max(5),
    opportunities: z.array(OpportunitySchema).max(3),
    seoFails: z.array(z.string()),
    suggestedAngle: z.string(),
    summary: z.string(),
});
export const AuditStatusSchema = z.enum(['done', 'template', 'pending']);
export const LeadSchema = z.object({
    placeId: z.string(),
    name: z.string(),
    phone: z.string().nullable(),
    address: z.string().nullable(),
    website: z.string().nullable(),
    mapsUrl: z.string(),
    rating: z.number().nullable(),
    reviewCount: z.number(),
    category: z.string().nullable(),
    city: z.string(),
    sector: z.string(),
    segment: SegmentSchema,
    size: SizeSchema,
    email: z.string().nullable(),
    facts: FactsSchema.nullable(),
    seoFails: z.array(z.string()),
    audit: AuditSchema.nullable(),
    auditStatus: AuditStatusSchema,
    priority: PrioritySchema,
    reasons: z.array(z.string()),
});
export const LeadsFileSchema = z.object({
    schemaVersion: z.literal(1),
    generatedAt: z.string(),
    query: z.object({ city: z.string(), sector: z.string() }),
    leads: z.array(LeadSchema),
});
