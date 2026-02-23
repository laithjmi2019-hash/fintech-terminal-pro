-- Add Public Insert/Update Policies so GitHub Actions (Cron) can write to the database
CREATE POLICY "Allow public insert to quant_metrics" 
    ON public.quant_metrics FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public update to quant_metrics" 
    ON public.quant_metrics FOR UPDATE USING (true);

CREATE POLICY "Allow public insert to macro_regime" 
    ON public.macro_regime FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public update to macro_regime" 
    ON public.macro_regime FOR UPDATE USING (true);
