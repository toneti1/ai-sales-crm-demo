const UNRELATED_CATEGORIES = [
    'supermercado',
    'hipermercado',
    'gasolinera',
    'estación de servicio',
    'taller',
    'mecanico',
    'restaurante',
    'bar',
    'cafetería',
    'hotel',
    'tienda de ropa',
    'banco',
    'cajero',
    'farmacia',
    'panadería',
    'centro comercial',
    'peluquería',
    'barbería',
    'estética',
    'tatuaje',
    'clínica veterinaria',
    'veterinario',
    'óptica',
    'floristería',
    'inmobiliaria',
    'agencia de viajes',
    'gimnasio',
    'autoescuela',
    'taller mecánico',
    'mudanzas',
    'cerrajero',
    'fontanería',
    'electricista',
    'pintor',
    'limpieza',
    'seguridad',
    'alarmas',
];
export function isRelevantCategory(category, sector) {
    if (!category)
        return true;
    const lowerCat = category.toLowerCase().trim();
    const lowerSector = sector.toLowerCase().trim();
    const isUnrelated = UNRELATED_CATEGORIES.some((c) => lowerCat.includes(c));
    if (isUnrelated && !lowerCat.includes(lowerSector) && !lowerSector.includes(lowerCat)) {
        return false;
    }
    return true;
}
